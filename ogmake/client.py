import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Union

from .errors import OgmakeApiError, OgmakeNetworkError, OgmakeRedirectError, parse_error_body
from .signing import canonical_query, decode_secret, sign_query

VERSION = "0.1.0"
DEFAULT_BASE_URL = "https://ogmake.com"
DEFAULT_TIMEOUT = 20.0
_MAX_FREE_RENDER_BYTES = 5 * 1024 * 1024


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


def _extras(fmt=None, preset=None, scale=None, v=None, bg=None) -> Dict[str, str]:
    out = {}
    for key, value in (("format", fmt), ("preset", preset), ("scale", scale), ("v", v), ("bg", bg)):
        if value:
            out[key] = value
    return out


def signed_image_url(
    key_id: str,
    signing_secret: str,
    template: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    format: Optional[str] = None,
    preset: Optional[str] = None,
    scale: Optional[str] = None,
    v: Optional[str] = None,
    bg: Optional[str] = None,
    base_url: str = DEFAULT_BASE_URL,
) -> str:
    """Builds ``{base}/i/{keyId}/{sig}?{canonical}``. ``signing_secret`` is the key's base64 secret."""
    query = {k: str(val) for k, val in (params or {}).items()}
    query["template"] = template
    query.update(_extras(format, preset, scale, v, bg))
    canonical = canonical_query(query)
    sig = sign_query(decode_secret(signing_secret), canonical)
    return "%s/i/%s/%s?%s" % (base_url.rstrip("/"), urllib.parse.quote(key_id, safe=""), sig, canonical)


def public_image_url(key_id: str, template_id: str, base_url: str = DEFAULT_BASE_URL) -> str:
    """Builds the unsigned ``{base}/p/{keyId}/{templateId}`` URL (key must be public + allow-list the template)."""
    return "%s/p/%s/%s" % (
        base_url.rstrip("/"),
        urllib.parse.quote(key_id, safe=""),
        urllib.parse.quote(template_id, safe=""),
    )


class Client:
    def __init__(self, api_key: Optional[str] = None, base_url: str = DEFAULT_BASE_URL, timeout: float = DEFAULT_TIMEOUT):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._opener = urllib.request.build_opener(_NoRedirect)

    def _request(self, method: str, path: str, body: Optional[dict] = None, auth: bool = True):
        headers = {"user-agent": "ogmake-python/" + VERSION}
        if auth:
            if not self.api_key:
                raise OgmakeApiError("unauthenticated", 0)
            headers["authorization"] = "Bearer " + self.api_key
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["content-type"] = "application/json"
        req = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            resp = self._opener.open(req, timeout=self.timeout)
            return resp.status, resp.headers, resp.read(_MAX_FREE_RENDER_BYTES + 1)
        except urllib.error.HTTPError as e:
            raw = e.read()
            if 300 <= e.code < 400:
                raise OgmakeRedirectError(e.code, e.headers.get("location")) from None
            info = parse_error_body(raw)
            raise OgmakeApiError(info["code"], e.code, info.get("detail")) from None
        except (urllib.error.URLError, OSError) as e:
            raise OgmakeNetworkError(e) from None

    def render(
        self,
        template: str,
        params: Optional[Dict[str, Union[str, int, list]]] = None,
        *,
        format: Optional[str] = None,
        preset: Optional[str] = None,
        scale: Optional[str] = None,
        v: Optional[str] = None,
        bg: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /v1/images (stored mode). Returns url, hash, cached, width, height, format, bytes, templateVersion."""
        body: Dict[str, Any] = {"template": template}
        if params:
            body["params"] = params
        body.update(_extras(format, preset, scale, v, bg))
        _, _, raw = self._request("POST", "/v1/images", body)
        return json.loads(raw)

    def render_html(
        self,
        html: str,
        width: int,
        height: int,
        *,
        css: Optional[str] = None,
        format: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /v1/images with raw ``html`` (+ optional ``css``). Returns url, hash, width, height, format, bytes, credits."""
        body: Dict[str, Any] = {"html": html, "width": width, "height": height}
        if css:
            body["css"] = css
        if format:
            body["format"] = format
        _, _, raw = self._request("POST", "/v1/images", body)
        return json.loads(raw)

    def screenshot(
        self,
        url: str,
        width: int,
        *,
        height: Optional[int] = None,
        full_page: Optional[bool] = None,
        format: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /v1/screenshot. Returns url, hash, width, height, fullPage, format, bytes, credits."""
        body: Dict[str, Any] = {"url": url, "width": width}
        if height is not None:
            body["height"] = height
        if full_page is not None:
            body["fullPage"] = full_page
        if format:
            body["format"] = format
        _, _, raw = self._request("POST", "/v1/screenshot", body)
        return json.loads(raw)

    def list_templates(self) -> Dict[str, Any]:
        _, _, raw = self._request("GET", "/v1/templates", auth=False)
        return json.loads(raw)

    def get_usage(self) -> Dict[str, Any]:
        _, _, raw = self._request("GET", "/v1/usage")
        return json.loads(raw)

    def free_render(self, title: str, description: Optional[str] = None, site: Optional[str] = None):
        """GET /v1/free/og. Returns ``(image_bytes, content_type)``."""
        q = {"title": title}
        if description:
            q["description"] = description
        if site:
            q["site"] = site
        _, headers, raw = self._request("GET", "/v1/free/og?" + urllib.parse.urlencode(q), auth=False)
        ctype = headers.get("content-type", "")
        if not ctype.lower().startswith("image/"):
            raise ValueError('ogmake free render returned an unexpected content-type: "%s"' % ctype)
        if len(raw) > _MAX_FREE_RENDER_BYTES:
            raise ValueError("ogmake free render exceeds %d bytes" % _MAX_FREE_RENDER_BYTES)
        return raw, ctype

    def signed_image_url(self, key_id: str, signing_secret: str, template: str, params=None, **kw) -> str:
        kw.setdefault("base_url", self.base_url)
        return signed_image_url(key_id, signing_secret, template, params, **kw)

    def public_image_url(self, key_id: str, template_id: str) -> str:
        return public_image_url(key_id, template_id, self.base_url)
