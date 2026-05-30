"""외부에서 보이는 공인 IP (업비트 허용 IP 등록용)."""

from __future__ import annotations

import httpx

_cached_ip: str | None = None


async def get_outbound_public_ip() -> str | None:
    global _cached_ip
    if _cached_ip:
        return _cached_ip
    urls = (
        "https://api.ipify.org",
        "https://ifconfig.me/ip",
    )
    async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
        for url in urls:
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    ip = resp.text.strip()
                    if ip and len(ip) < 64:
                        _cached_ip = ip
                        return ip
            except Exception:
                continue
    return None
