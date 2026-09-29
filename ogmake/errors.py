"""Typed errors. The API answers failures with JSON ``{"error": code, "detail": [...]}``."""
from typing import Any, List, Optional


class OgmakeError(Exception):
    """Base class for every error this SDK raises."""


class OgmakeApiError(OgmakeError):
    def __init__(self, code: str, status: int, detail: Optional[List[dict]] = None) -> None:
        super().__init__("ogmake API error: %s (HTTP %d)" % (code, status))
        self.code = code
        self.status = status
        self.detail = detail


class OgmakeNetworkError(OgmakeError):
    def __init__(self, cause: BaseException) -> None:
        super().__init__("ogmake network error: %s" % cause)
        self.cause = cause


class OgmakeRedirectError(OgmakeError):
    """The SDK never follows redirects (a Bearer key must not be replayed elsewhere)."""

    def __init__(self, status: int, location: Optional[str]) -> None:
        super().__init__("ogmake API returned a redirect (HTTP %d); the SDK never follows redirects" % status)
        self.status = status
        self.location = location


def parse_error_body(raw: bytes) -> dict:
    import json

    try:
        parsed: Any = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {"code": "unknown_error"}
    if not isinstance(parsed, dict):
        return {"code": "unknown_error"}
    err = parsed.get("error")
    code = err if isinstance(err, str) and err else "unknown_error"
    detail = None
    if isinstance(parsed.get("detail"), list):
        detail = [
            d
            for d in parsed["detail"]
            if isinstance(d, dict) and isinstance(d.get("field"), str) and isinstance(d.get("message"), str)
        ] or None
    return {"code": code, "detail": detail}
