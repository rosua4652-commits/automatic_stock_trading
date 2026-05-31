"""AIDI 애플리케이션 로그 — 버튼·백테스트·스캔 등 비즈니스 이벤트."""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

AIDI_LOGGER_NAME = "aidi"

# Windows cp949 콘솔에서 깨지는 문자 (em dash 등)
_CONSOLE_UNSAFE = str.maketrans(
    {
        "\u2014": "-",  # —
        "\u2013": "-",  # –
        "\u2212": "-",  # −
        "\u00a0": " ",
        "\u00b7": " ",  # middle dot
    }
)


def sanitize_log_text(msg: str) -> str:
    if not msg:
        return msg
    return msg.translate(_CONSOLE_UNSAFE)


def _win_console_encoding() -> str:
    enc = getattr(sys.stdout, "encoding", None) or ""
    enc = enc.lower().replace("_", "-")
    if enc.startswith("utf"):
        return "utf-8"
    if enc in ("cp949", "euc-kr", "mbcs", "ansi", "cp936"):
        return "cp949"
    return "utf-8"


class ConsoleSafeFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return sanitize_log_text(super().format(record))


class WindowsAwareStreamHandler(logging.StreamHandler):
    """Windows: UTF-8 buffer or cp949 — 한글 깨짐 방지."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = sanitize_log_text(self.format(record))
            term = self.terminator
            line = msg + term
            stream = self.stream
            enc = _win_console_encoding() if sys.platform == "win32" else "utf-8"
            buf = getattr(stream, "buffer", None)
            if enc == "utf-8" and buf is not None:
                buf.write(line.encode("utf-8", errors="replace"))
                buf.flush()
                return
            if sys.platform == "win32" and enc == "cp949":
                safe = line.encode("cp949", errors="replace").decode("cp949")
                stream.write(safe)
                self.flush()
                return
            stream.write(line)
            self.flush()
        except UnicodeEncodeError:
            try:
                stream = self.stream
                buf = getattr(stream, "buffer", None)
                if buf is not None:
                    buf.write(
                        (sanitize_log_text(self.format(record)) + self.terminator).encode(
                            "utf-8", errors="replace"
                        )
                    )
                    buf.flush()
                else:
                    stream.write(
                        sanitize_log_text(self.format(record)) + self.terminator
                    )
                    self.flush()
            except Exception:
                self.handleError(record)
        except Exception:
            self.handleError(record)


def _configure_windows_console_utf8() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


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


def _install_root_handler(handler: logging.Handler, fmt: logging.Formatter) -> None:
    root = logging.getLogger()
    handler.setFormatter(fmt)
    if not root.handlers:
        root.addHandler(handler)
        root.setLevel(logging.INFO)
        return
    replaced = False
    for h in list(root.handlers):
        if isinstance(h, logging.StreamHandler):
            root.removeHandler(h)
            if not replaced:
                nh = WindowsAwareStreamHandler(h.stream)
                nh.setFormatter(fmt)
                nh.setLevel(h.level)
                root.addHandler(nh)
                replaced = True
    if not replaced:
        root.addHandler(handler)
    root.setLevel(logging.INFO)


def setup_aidi_logging() -> logging.Logger:
    """uvicorn 시작 전·lifespan에서 한 번 호출."""
    _configure_windows_console_utf8()
    fmt = ConsoleSafeFormatter(
        "%(asctime)s | AIDI | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _install_root_handler(WindowsAwareStreamHandler(sys.stdout), fmt)

    for name in ("aidi", "app", "app.engine", "app.market"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.INFO)
        lg.propagate = True

    for name in ("httpx", "httpcore", "h11"):
        logging.getLogger(name).setLevel(logging.WARNING)

    aidi = logging.getLogger(AIDI_LOGGER_NAME)

    access = logging.getLogger("uvicorn.access")
    access.addFilter(QuietPollingAccessFilter())

    logging.getLogger("uvicorn.error").setLevel(logging.INFO)

    aidi.info(
        "로그 모드 - 스캔·자동투자·버튼·백테스트 기록 "
        "(HTTP 요청·차트/상태 폴링은 생략)"
    )
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
    ("/api/data/reset-paper", "모의투자 초기화"),
    ("/api/data/reset-backtest", "백테스트 데이터 초기화"),
    ("/api/risk/reset-kill", "킬 스위치 해제"),
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
