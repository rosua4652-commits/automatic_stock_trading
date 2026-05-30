from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import asdict
from typing import Any

from .config import AppConfig
from .strategy import Signal


class AIAnalysisClient:
    def __init__(self, config: AppConfig, timeout: int = 30) -> None:
        self.enabled = config.ai_enabled and bool(config.cursor_api_key)
        self.api_key = config.cursor_api_key
        self.base_url = config.ai_base_url
        self.model = config.ai_model
        self.timeout = timeout

    def summarize_signal(self, signal: Signal, market_context: dict[str, Any] | None = None) -> str:
        if not self.enabled:
            return "AI analysis disabled. Set AI_ENABLED=true and CURSOR_API_KEY to enable summaries."

        prompt = {
            "role": "user",
            "content": (
                "You are a cautious Korean crypto scalping analyst. "
                "Do not promise profits. Explain entry quality, risk, and invalidation.\n\n"
                f"Market context: {json.dumps(market_context or {}, ensure_ascii=False)}\n"
                f"Signal: {json.dumps(_signal_to_safe_dict(signal), ensure_ascii=False)}"
            ),
        }
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return a concise Korean analysis with sections: 핵심 판단, 진입 조건, 위험 요소, 손절/익절. "
                        "Never claim certainty or guaranteed profit."
                    ),
                },
                prompt,
            ],
            "temperature": 0.2,
        }
        return self._post_chat(payload)

    def summarize_settings(self, settings: dict[str, Any], advice: dict[str, Any]) -> str:
        if not self.enabled:
            return "AI 설정 분석이 비활성화되어 있습니다. AI_ENABLED=true와 CURSOR_API_KEY를 설정하세요."

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "너는 한국어로 답하는 보수적인 코인 단타 리스크 매니저다. "
                        "수익 보장을 하지 말고, 설정의 위험/수정점/운영 순서를 짧고 명확하게 설명해라."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "아래 업비트 단타 봇 설정과 rule 기반 점검 결과를 보고 설정을 평가해줘.\n"
                        "섹션은 '종합 판단', '위험 설정', '추천 조정', '실행 전 체크'로 작성해.\n\n"
                        f"설정: {json.dumps(settings, ensure_ascii=False)}\n"
                        f"점검 결과: {json.dumps(advice, ensure_ascii=False)}"
                    ),
                },
            ],
            "temperature": 0.2,
        }
        return self._post_chat(payload)

    def _post_chat(self, payload: dict[str, Any]) -> str:
        request = urllib.request.Request(
            self.base_url,
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return _friendly_ai_error(exc.code, body)
        except Exception as exc:
            return f"AI 분석 실패: {type(exc).__name__}: {exc}"

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return f"AI 응답 형식이 예상과 다릅니다: {json.dumps(data, ensure_ascii=False)[:500]}"


def _signal_to_safe_dict(signal: Signal) -> dict[str, Any]:
    data = asdict(signal)
    indicators = data.get("indicators")
    if indicators:
        data["indicators"] = {
            key: round(value, 6) if isinstance(value, float) else value
            for key, value in indicators.items()
        }
    plan = data.get("plan")
    if plan:
        data["plan"] = {
            key: round(value, 6) if isinstance(value, float) else value
            for key, value in plan.items()
        }
    return data


def _friendly_ai_error(status_code: int, body: str) -> str:
    if status_code == 404:
        return (
            "AI API 호출 실패: 현재 설정된 AI_BASE_URL이 채팅 분석 엔드포인트가 아닙니다. "
            "Cursor crsr_ 키는 일반 OpenAI 호환 chat completions 용도가 아닐 수 있습니다. "
            "앱은 rule 기반 분석은 계속 제공하며, LLM 분석을 쓰려면 OpenAI 호환 AI_BASE_URL과 해당 API 키를 설정하세요."
        )
    if status_code in {401, 403}:
        return "AI API 인증 실패: API 키 또는 권한을 확인하세요."
    return f"AI API 호출 실패: HTTP {status_code} {body[:300]}"
