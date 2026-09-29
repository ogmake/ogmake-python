import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from ogmake import (Client, OgmakeApiError, OgmakeNetworkError, OgmakeRedirectError, canonical_query,
                    decode_secret, public_image_url, sign_query, signed_image_url)

# Shared vectors: packages/core/src/signing.test.ts, packages/laravel-ogmake/tests/SigningTest.php
SECRET = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
CANONICAL = "format=png&template=basic&title=Hello%20World"
SIG = "W8Xvrf9UTFKbVVQtofHq7A2ljK9z-nvJUL3B-rB7MY8"
ASTRAL_CANONICAL = "%F0%9F%98%80=astral&%EE%80%80=pua"
ASTRAL_SIG = "Zr62H77WBS8WhCLT5Nt-vSrQ1Ldiot7_-W1XE335SPU"


def test_vector():
    p = {"template": "basic", "title": "Hello World", "format": "png", "sig": "x", "debug": "1"}
    assert canonical_query(p) == CANONICAL
    assert sign_query(decode_secret(SECRET), CANONICAL) == SIG


def test_astral_vector():
    c = canonical_query({"\U0001F600": "astral", "": "pua"})
    assert c == ASTRAL_CANONICAL
    assert sign_query(decode_secret(SECRET), c) == ASTRAL_SIG


def test_reserved_chars_and_bad_secret():
    assert canonical_query({"q": "a!b'c(d)e*f"}) == "q=a%21b%27c%28d%29e%2Af"
    with pytest.raises(ValueError):
        decode_secret("!!!")


def test_signed_url():
    url = signed_image_url("key1", SECRET, "basic", {"title": "Hello World"}, format="png")
    assert url == "https://ogmake.com/i/key1/%s?%s" % (SIG, CANONICAL)


def test_public_url():
    assert public_image_url("k", "a b", "https://x.test/") == "https://x.test/p/k/a%20b"


class _H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json", extra=None):
        self.send_response(code)
        self.send_header("content-type", ctype)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        body = json.loads(self.rfile.read(n))
        if self.headers.get("authorization") != "Bearer og_live_x":
            return self._send(401, b'{"error":"unauthorized"}')
        if self.path == "/v1/screenshot":
            self.server.last = body
            return self._send(201, json.dumps({"url": "https://ogmake.com/s/x.png", "credits": 3}).encode())
        if "html" in body:
            self.server.last = body
            return self._send(201, json.dumps({"url": "https://ogmake.com/s/y.png", "credits": 2}).encode())
        if body["template"] == "bad":
            return self._send(400, b'{"error":"invalid_input","detail":[{"field":"title","message":"required"}]}')
        self._send(200, json.dumps({"url": "https://ogmake.com/s/h.png", "hash": "h", "cached": False}).encode())

    def do_GET(self):
        if self.path == "/redir":
            return self._send(302, b"", extra={"location": "https://evil.test"})
        if self.path == "/v1/templates":
            return self._send(200, b'{"templates":[]}')
        if self.path.startswith("/v1/free/og"):
            return self._send(200, b"\x89PNG", "image/png")
        self._send(500, b"<html>")


@pytest.fixture()
def srv():
    server = HTTPServer(("127.0.0.1", 0), _H)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server
    server.shutdown()


@pytest.fixture()
def base(srv):
    return "http://127.0.0.1:%d" % srv.server_port


def test_render_html(srv, base):
    c = Client("og_live_x", base)
    out = c.render_html("<h1>Hi</h1>", 1200, 630, css="h1{color:red}", format="webp")
    assert out["credits"] == 2
    assert srv.last == {"html": "<h1>Hi</h1>", "width": 1200, "height": 630, "css": "h1{color:red}", "format": "webp"}
    c.render_html("<p>x</p>", 100, 100)
    assert srv.last == {"html": "<p>x</p>", "width": 100, "height": 100}
    with pytest.raises(OgmakeApiError) as e:
        Client("wrong", base).render_html("<p/>", 100, 100)
    assert e.value.code == "unauthorized"


def test_screenshot(srv, base):
    c = Client("og_live_x", base)
    assert c.screenshot("https://example.com/", 1280, height=800, full_page=True, format="jpg")["credits"] == 3
    assert srv.last == {"url": "https://example.com/", "width": 1280, "height": 800, "fullPage": True, "format": "jpg"}
    c.screenshot("https://example.com/", 1280)
    assert srv.last == {"url": "https://example.com/", "width": 1280}


def test_render_ok_and_errors(base):
    c = Client("og_live_x", base)
    assert c.render("basic", {"title": "t"})["hash"] == "h"
    with pytest.raises(OgmakeApiError) as e:
        c.render("bad")
    assert e.value.code == "invalid_input" and e.value.status == 400 and e.value.detail[0]["field"] == "title"
    with pytest.raises(OgmakeApiError) as e:
        Client("wrong", base).render("basic")
    assert e.value.code == "unauthorized"
    with pytest.raises(OgmakeApiError) as e:
        Client(None, base).render("basic")
    assert e.value.code == "unauthenticated" and e.value.status == 0


def test_misc(base):
    c = Client(None, base)
    assert c.list_templates() == {"templates": []}
    assert c.free_render("hi")[1] == "image/png"
    with pytest.raises(OgmakeRedirectError):
        c._request("GET", "/redir", auth=False)
    with pytest.raises(OgmakeApiError) as e:
        c._request("GET", "/nope", auth=False)
    assert e.value.code == "unknown_error"
    with pytest.raises(OgmakeNetworkError):
        Client("k", "http://127.0.0.1:1").render("basic")
