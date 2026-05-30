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
            return f"AI analysis failed: HTTP {exc.code} {body[:300]}"
        except Exception as exc:  # Keep trading logic independent from AI availability.
            return f"AI analysis failed: {type(exc).__name__}: {exc}"

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return f"AI analysis returned an unexpected response: {json.dumps(data)[:500]}"


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
