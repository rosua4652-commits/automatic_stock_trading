"""업비트 등 외부 API — IPv4 직접 연결 (IPv6·프록시로 IP 불일치 방지)."""

from __future__ import annotations

import socket

import httpx

_shared_ipv4: httpx.AsyncClient | None = None
_shared_upbit: httpx.AsyncClient | None = None

UPBIT_HOST = "https://api.upbit.com"


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


def shared_ipv4_client() -> httpx.AsyncClient:
    """일반 IPv4 조회용."""
    global _shared_ipv4
    if _shared_ipv4 is None or _shared_ipv4.is_closed:
        _shared_ipv4 = ipv4_async_client(timeout=25.0)
    return _shared_ipv4


def shared_upbit_client() -> httpx.AsyncClient:
    """업비트 API + IP 조회가 동일 연결 풀을 사용."""
    global _shared_upbit
    if _shared_upbit is None or _shared_upbit.is_closed:
        _shared_upbit = ipv4_async_client(base_url=UPBIT_HOST, timeout=25.0)
    return _shared_upbit


async def outbound_ipv4_via_same_stack() -> str | None:
    """Upbit와 동일 httpx 클라이언트로 보이는 공인 IPv4."""
    client = shared_upbit_client()
    urls = ("https://api.ipify.org", "https://ipv4.icanhazip.com")
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
