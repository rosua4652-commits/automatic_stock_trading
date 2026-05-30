"""외부에서 보이는 공인 IP (업비트 허용 IP 등록용)."""

from __future__ import annotations

import httpx

from app.market.ipv4_http import outbound_ipv4_via_same_stack

_cached_ip: str | None = None


async def get_outbound_public_ip() -> str | None:
    """Upbit와 동일 스택(IPv4·프록시 무시) 우선."""
    global _cached_ip
    ip4 = await outbound_ipv4_via_same_stack()
    if ip4:
        _cached_ip = ip4
        return ip4
    if _cached_ip:
        return _cached_ip
    async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
        try:
            resp = await client.get("https://api.ipify.org")
            if resp.status_code == 200:
                text = resp.text.strip()
                if text:
                    _cached_ip = text
                    return text
        except Exception:
            pass
    return None
