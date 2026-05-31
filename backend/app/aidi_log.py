"""AIDI 애플리케이션 로그 — 버튼·백테스트·스캔 등 비즈니스 이벤트."""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

AIDI_LOGGER_NAME = "aidi"

# uvicorn access 로그에서 숨길 폴링 경로 (차트·상태)
_QUIET_ACCESS = re.compile(
    r'"(?:GET|HEAD) /api/(?:chart/[^"]+|status)(?:\?[^"]*)? HTTP'
)


class QuietPollingAccessFilter(logging.Filter):
    """GET /api/chart/*, GET /api/status 반복 로그 억제."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if _QUIET_ACCESS.search(msg):
            return False
        return True


def setup_aidi_logging() -> logging.Logger:
    """uvicorn 시작 전·lifespan에서 한 번 호출."""
    fmt = logging.Formatter(
        "%(asctime)s | AIDI | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(fmt)
        root.addHandler(handler)
    root.setLevel(logging.INFO)

    for name in ("aidi", "app", "app.engine", "app.market"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.INFO)
        lg.propagate = True

    aidi = logging.getLogger(AIDI_LOGGER_NAME)
    if not aidi.handlers:
        # root로만 전파
        pass

    access = logging.getLogger("uvicorn.access")
    access.addFilter(QuietPollingAccessFilter())

    logging.getLogger("uvicorn.error").setLevel(logging.INFO)

    aidi.info("로그 모드 — 버튼·백테스트·스캔 상세 기록 (차트/상태 폴링은 생략)")
    return aidi


def get_aidi_logger() -> logging.Logger:
    return logging.getLogger(AIDI_LOGGER_NAME)


def log_event(message: str, *, level: int = logging.INFO) -> None:
    get_aidi_logger().log(level, message)


def log_action(
    label: str,
    detail: str = "",
    *,
    ok: bool | None = None,
    ms: float | None = None,
) -> None:
    """사용자 액션(버튼·API) 한 줄."""
    parts = [f"[{label}]"]
    if ok is not None:
        parts.append("성공" if ok else "실패")
    if detail:
        parts.append(detail.strip())
    if ms is not None:
        parts.append(f"({ms:.0f}ms)")
    log_event(" ".join(parts))


# POST 경로 → 한글 라벨 (와일드카드는 prefix 매칭)
_ACTION_ROUTES: list[tuple[str, str]] = [
    ("/api/bot/start", "분석/자동투자 시작"),
    ("/api/bot/stop", "분석 중지"),
    ("/api/config", "설정 저장"),
    ("/api/credentials/test", "API 연결 테스트"),
    ("/api/account/sync", "계정 강제 동기화"),
    ("/api/recommendations/apply", "투자 제안 승인 매수"),
    ("/api/trade/buy", "수동 매수"),
    ("/api/trade/sell", "수동 매도"),
    ("/api/trade/sell-all", "전체 매도"),
    ("/api/signals/scan/", "롱·숏 분석"),
    ("/api/position/", "포지션 손익절·제외"),
    ("/api/view/", "차트 탭 선택"),
    ("/api/chart/select/", "차트 종목 선택"),
]


def action_label_for_path(path: str, method: str) -> str | None:
    if method.upper() != "POST":
        return None
    p = path.split("?", 1)[0]
    for prefix, label in _ACTION_ROUTES:
        if p.startswith(prefix):
            if prefix == "/api/signals/scan/":
                side = p.rsplit("/", 1)[-1].lower()
                if side == "long":
                    return "롱 분석 버튼"
                if side == "short":
                    return "숏 분석 버튼"
                return label
            if "/exit-plan" in p:
                sym = p.split("/api/position/", 1)[-1].split("/")[0]
                return f"손익절 설정 · {sym}"
            if "/exclude" in p:
                sym = p.split("/api/position/", 1)[-1].split("/")[0]
                return f"자동매매 제외 · {sym}"
            if prefix == "/api/view/":
                sym = p.rsplit("/", 1)[-1]
                return f"탭 선택 · {sym}"
            return label
    return None


def summarize_json_response(body: Any, max_len: int = 200) -> str:
    if not isinstance(body, dict):
        return ""
    for key in ("message", "switch_message", "detail", "error"):
        v = body.get(key)
        if v and isinstance(v, str):
            s = v.strip().replace("\n", " ")
            return s[:max_len] if len(s) > max_len else s
    if body.get("ok") is False and body.get("upbit_error_message"):
        return str(body.get("upbit_error_message"))[:max_len]
    return ""
