"""업비트 등 외부 API — IPv4 직접 연결 (IPv6·프록시로 IP 불일치 방지)."""

from __future__ import annotations

import socket

import httpx


def ipv4_async_client(**kwargs) -> httpx.AsyncClient:
    """Windows: IPv6로 나가면 업비트 허용 IP(IPv4)와 달라질 수 있음."""
    transport = httpx.AsyncHTTPTransport(
        local_address="0.0.0.0",
        retries=1,
    )
    return httpx.AsyncClient(
        transport=transport,
        trust_env=False,
        **kwargs,
    )


async def outbound_ipv4_via_same_stack() -> str | None:
    """Upbit 요청과 같은 httpx 설정으로 보이는 공인 IPv4."""
    urls = ("https://api.ipify.org", "https://ipv4.icanhazip.com")
    async with ipv4_async_client(timeout=8.0) as client:
        for url in urls:
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    ip = resp.text.strip()
                    if ip and "." in ip and ":" not in ip:
                        return ip
            except Exception:
                continue
    return None


def upbit_resolved_ipv4() -> list[str]:
    try:
        infos = socket.getaddrinfo(
            "api.upbit.com", 443, socket.AF_INET, socket.SOCK_STREAM
        )
        return list(dict.fromkeys(i[4][0] for i in infos))
    except OSError:
        return []
