"""Upbit API 오류 파싱."""

from __future__ import annotations

import json

from app.market.ipv4_http import outbound_ipv4_via_same_stack
from app.market.network_info import get_outbound_public_ip


def parse_upbit_error_body(text: str) -> tuple[str, str]:
    try:
        data = json.loads(text)
        err = data.get("error") if isinstance(data, dict) else None
        if isinstance(err, dict):
            return str(err.get("name") or ""), str(err.get("message") or text)
    except Exception:
        pass
    return "", text


async def parse_upbit_error(text: str, access_hint: str = "") -> RuntimeError:
    name, msg = parse_upbit_error_body(text)
    key_note = f" (Access Key: {access_hint})" if access_hint else ""
    if name == "no_authorization_ip" or "no_authorization_ip" in text:
        ip = await outbound_ipv4_via_same_stack() or await get_outbound_public_ip()
        ip_hint = f" 나가는 IP: {ip}." if ip else ""
        return RuntimeError(
            "업비트 API: 허용 IP 오류(no_authorization_ip)."
            + ip_hint
            + key_note
            + " Open API에서 이 Access Key에 위 IP를 등록하세요."
        )
    if name in ("invalid_access_key", "invalid_secret_key"):
        return RuntimeError(f"업비트 API: {name} — {msg}{key_note}")
    if name in ("invalid_query_payload", "jwt_verification", "expired_access_key"):
        return RuntimeError(f"업비트 API: {name} — {msg}{key_note}")
    if name in ("not_found_market",) or "notfoundmarket" in (name or "").lower():
        return RuntimeError(
            f"업비트에 없는 코인(마켓)입니다 — {msg}{key_note} "
            "AIDI는 바이낸스 USDT 목록도 보지만, 업비트 실거래는 KRW 상장 종목만 주문합니다."
        )
    if name:
        return RuntimeError(f"업비트 API [{name}]: {msg}{key_note}")
    return RuntimeError(f"Upbit: {msg or text}{key_note}")
