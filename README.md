# ogmake (Python)

Thin Python SDK for the [ogmake](https://ogmake.com) OG image API. Standard library only.

## Install

```sh
pip install git+https://github.com/ogmake/ogmake-python
```

## Examples

Signed URL (computed locally; the signing secret never leaves your process):

```python
from ogmake import signed_image_url

url = signed_image_url("KEY_ID", "BASE64_SIGNING_SECRET", "basic",
                       {"title": "Hello World"}, format="png")
```

Public (unsigned) URL for a key marked public with the template allow-listed:

```python
from ogmake import public_image_url

url = public_image_url("KEY_ID", "basic") + "?title=Hello"
```

Stored render with typed errors:

```python
from ogmake import Client, OgmakeApiError

client = Client(api_key="og_live_...")
try:
    result = client.render("basic", {"title": "Hello"}, format="png")
    print(result["url"])
except OgmakeApiError as e:
    print(e.code, e.status, e.detail)
```

Errors: `OgmakeApiError` (`code`, `status`, `detail`), `OgmakeNetworkError`, `OgmakeRedirectError` (redirects are never followed). Raw HTML render (2 credits): `client.render_html(html, 1200, 630, css=..., format="png")`. Page screenshot (3 credits): `client.screenshot("https://example.com/", 1280, height=800, full_page=False, format="png")`. Also `list_templates()`, `get_usage()`, `free_render()`.

Tests: `python3 -m venv .venv && .venv/bin/pip install pytest && .venv/bin/python -m pytest`.

MIT licensed.

Support: support@ogmake.com
