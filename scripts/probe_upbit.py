#!/usr/bin/env python3
"""PC에서 저장된 업비트 키 + 나가는 IP + 업비트 응답 확인 (서버 구버전이어도 동작)."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# backend 패키지
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.market.ipv4_http import outbound_ipv4_via_same_stack  # noqa: E402
from app.market.upbit_client import upbit_client  # noqa: E402
from app.storage.credentials import load_credentials, mask_key  # noqa: E402


async def main() -> None:
    cred = load_credentials()
    ak = (cred.get("api_access_key") or "").strip()
    sk = (cred.get("api_secret_key") or "").strip()
    print("=== AIDI PC Upbit probe ===")
    print("credentials.json:", ROOT / "backend" / "data" / "credentials.json")
    print("saved_access_key:", mask_key(ak, 4) if ak else "(없음)")
    if not ak or not sk:
        print("\n키 없음 → AIDI 설정에서 Access+Secret 입력 후 [저장] 하세요.")
        return
    ip = await outbound_ipv4_via_same_stack()
    print("outbound_ipv4 (업비트와 동일 경로):", ip or "(확인 실패)")
    print("\n업비트 /v1/accounts 호출...")
    upbit_client.configure(ak, sk)
    probe = await upbit_client.probe_accounts()
    print(json.dumps(probe, ensure_ascii=False, indent=2))
    if probe.get("ok"):
        print("\n→ 연동 OK. AIDI에서도 연결 테스트/실거래가 되어야 합니다.")
    elif probe.get("upbit_error_name") == "no_authorization_ip":
        print(
            f"\n→ 업비트 Open API 키 [{probe.get('access_key_hint')}] 에 "
            f"IP [{ip}] 가 등록돼 있는지 확인하세요."
        )
        print("  (다른 키에만 IP 등록했거나, AIDI에 예전 키가 저장된 경우 동일 증상)")
    elif probe.get("upbit_error_name") in ("invalid_access_key", "invalid_secret_key"):
        print("\n→ 키 오류. Access·Secret 한 쌍을 새로 붙여넣고 저장하세요.")


if __name__ == "__main__":
    asyncio.run(main())
