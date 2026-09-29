"""Request signing: same algorithm as packages/core/src/signing.ts."""
import base64
import hashlib
import hmac
import urllib.parse
from typing import Dict, List

_EXCLUDED = {"sig", "debug"}


def _rfc3986(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def _utf16_key(value: str) -> List[int]:
    # JS default string sort = UTF-16 code unit order, not code point order.
    units: List[int] = []
    for ch in value:
        cp = ord(ch)
        if cp > 0xFFFF:
            cp -= 0x10000
            units.append(0xD800 + (cp >> 10))
            units.append(0xDC00 + (cp & 0x3FF))
        else:
            units.append(cp)
    return units


def canonical_query(params: Dict[str, str]) -> str:
    filtered = {k: v for k, v in params.items() if k not in _EXCLUDED}
    return "&".join(
        "%s=%s" % (_rfc3986(k), _rfc3986(v))
        for k, v in sorted(filtered.items(), key=lambda kv: _utf16_key(kv[0]))
    )


def decode_secret(secret_base64: str) -> bytes:
    try:
        return base64.b64decode(secret_base64, validate=True)
    except ValueError:
        raise ValueError("invalid_signing_secret") from None


def sign_query(secret: bytes, canonical: str) -> str:
    mac = hmac.new(secret, canonical.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).rstrip(b"=").decode("ascii")
