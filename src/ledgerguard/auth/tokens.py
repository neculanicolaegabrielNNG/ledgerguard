from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime
from typing import Any

from ledgerguard.common.errors import unauthorized


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


# ————————————————————————————————————————

def _decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# ————————————————————————————————————————

def _signature(secret: str, signing_input: str) -> str:
    return _encode(hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest())


# ————————————————————————————————————————

def issue_token(secret: str, claims: dict[str, Any], now: datetime, ttl_seconds: int) -> str:
    issued = int(now.timestamp())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {**claims, "iat": issued, "exp": issued + ttl_seconds}
    signing_input = (
        f"{_encode(json.dumps(header, separators=(',', ':')).encode())}."
        f"{_encode(json.dumps(payload, separators=(',', ':')).encode())}"
    )
    return f"{signing_input}.{_signature(secret, signing_input)}"


# ————————————————————————————————————————

def verify_token(secret: str, token: str, now: datetime) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise unauthorized()
    signing_input = f"{parts[0]}.{parts[1]}"
    if not hmac.compare_digest(_signature(secret, signing_input), parts[2]):
        raise unauthorized()
    try:
        header = json.loads(_decode(parts[0]))
        payload = json.loads(_decode(parts[1]))
    except (ValueError, UnicodeError) as error:
        raise unauthorized() from error
    if header.get("alg") != "HS256" or not isinstance(payload, dict):
        raise unauthorized()
    if int(payload.get("exp", 0)) <= int(now.timestamp()):
        raise unauthorized("Sesiunea a expirat.")
    return payload
