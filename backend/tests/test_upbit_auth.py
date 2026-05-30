"""업비트 JWT — 공식 문서와 동일한지 검증."""

import hashlib
import uuid
from urllib.parse import unquote, urlencode

import jwt as pyjwt

from app.market.upbit_auth import JWT_ALG, build_query_string, create_jwt


def test_jwt_uses_hs512():
    token = create_jwt("test_access", "test_secret", "")
    assert pyjwt.get_unverified_header(token)["alg"] == "HS512"


def test_query_string_matches_docs():
    body = {
        "market": "KRW-BTC",
        "side": "bid",
        "volume": "0.01",
        "price": "100.0",
        "ord_type": "limit",
    }
    qs = build_query_string(body)
    assert qs == "market=KRW-BTC&side=bid&volume=0.01&price=100.0&ord_type=limit"


def test_query_hash_in_payload():
    qs = "market=KRW-BTC&limit=10"
    token = create_jwt("ak", "sk", qs)
    payload = pyjwt.decode(token, "sk", algorithms=[JWT_ALG])
    expected = hashlib.sha512(qs.encode()).hexdigest()
    assert payload["query_hash"] == expected
    assert payload["query_hash_alg"] == "SHA512"
