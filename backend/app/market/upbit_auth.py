"""업비트 Open API JWT 인증 — 공식 문서 기준.

https://docs.upbit.com/kr/reference/auth
https://docs.upbit.com/kr/docs/first-exchange-api-call
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any
from urllib.parse import unquote, urlencode

import jwt

JWT_ALG = "HS512"
HASH_ALG = "SHA512"


def build_query_string(params: dict[str, Any] | None) -> str:
    """공식: unquote(urlencode(params, doseq=True))"""
    if not params:
        return ""
    return unquote(urlencode(params, doseq=True))


def create_jwt(access_key: str, secret_key: str, query_string: str = "") -> str:
    """Exchange API 인증 토큰 (HS512)."""
    payload: dict[str, Any] = {
        "access_key": access_key,
        "nonce": str(uuid.uuid4()),
    }
    if query_string:
        digest = hashlib.sha512(query_string.encode("utf-8")).hexdigest()
        payload["query_hash"] = digest
        payload["query_hash_alg"] = HASH_ALG
    token = jwt.encode(payload, secret_key, algorithm=JWT_ALG)
    return token if isinstance(token, str) else token.decode("utf-8")


def auth_headers(access_key: str, secret_key: str, query_string: str = "") -> dict[str, str]:
    token = create_jwt(access_key, secret_key, query_string)
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
