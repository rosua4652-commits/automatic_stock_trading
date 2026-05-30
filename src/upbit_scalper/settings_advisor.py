from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .config import AppConfig


@dataclass(frozen=True)
class SettingsFinding:
    severity: str
    title: str
    detail: str
    recommendation: str


@dataclass(frozen=True)
class SettingsAdvice:
    safety_score: int
    mode: str
    findings: list[SettingsFinding]
    suggested_overrides: dict[str, Any]
    summary: str


def analyze_investment_settings(config: AppConfig, interval_seconds: int) -> SettingsAdvice:
    findings: list[SettingsFinding] = []
    suggestions: dict[str, Any] = {}
    risk = config.risk

    position_pct = (risk.max_position_krw / risk.total_budget_krw * 100) if risk.total_budget_krw else 0
    min_position_pct = (risk.min_position_krw / risk.total_budget_krw * 100) if risk.total_budget_krw else 0
    daily_loss_pct = (risk.daily_loss_limit_krw / risk.total_budget_krw * 100) if risk.total_budget_krw else 0
    expected_net = risk.take_profit_pct - risk.round_trip_cost_pct
    reward_risk = risk.take_profit_pct / risk.stop_loss_pct if risk.stop_loss_pct else 0

    if config.trading_mode == "live" and not config.live_trading_enabled:
        findings.append(
            SettingsFinding(
                "warning",
                "실거래 모드 선택됨",
                "UI 설정은 live지만 .env의 LIVE_TRADING_ENABLED가 꺼져 있어 실제 주문은 paper로 보호됩니다.",
                "실거래 전 paper 로그를 충분히 확인하고, 필요한 경우에만 .env에서 실거래를 켜세요.",
            )
        )

    if not config.ai_enabled:
        findings.append(
            SettingsFinding(
                "info",
                "AI 분석 비활성화",
                "후보 신호와 설정 점검은 rule 기반으로 동작하지만 AI 해석은 꺼져 있습니다.",
                "시장/설정 해석을 같이 보려면 AI 분석을 활성화하세요.",
            )
        )
        suggestions["ai_enabled"] = True

    if risk.total_budget_krw <= 0:
        findings.append(
            SettingsFinding("critical", "총 운용 예산 오류", "총 운용 예산이 0 이하입니다.", "총 운용 예산을 0보다 크게 설정하세요.")
        )
        suggestions["total_budget_krw"] = 50_000

    if risk.min_position_krw > risk.max_position_krw:
        findings.append(
            SettingsFinding(
                "critical",
                "최소 진입금이 최대 진입금보다 큼",
                "포지션 계획이 왜곡될 수 있습니다.",
                "최소 진입금을 최대 진입금 이하로 낮추세요.",
            )
        )
        suggestions["min_position_krw"] = risk.max_position_krw

    if position_pct > 30:
        findings.append(
            SettingsFinding(
                "warning",
                "1회 진입 비중이 큼",
                f"1회 최대 진입금이 총 예산의 {position_pct:.1f}%입니다.",
                "초기 단타 테스트는 1회 진입을 총 예산의 10~20% 안쪽으로 제한하는 편이 안전합니다.",
            )
        )
        suggestions["max_position_krw"] = round(risk.total_budget_krw * 0.2)
    elif position_pct < 5 and risk.total_budget_krw >= 50_000:
        findings.append(
            SettingsFinding(
                "info",
                "1회 진입 비중이 낮음",
                f"1회 최대 진입금이 총 예산의 {position_pct:.1f}%입니다.",
                "검증 단계에서는 괜찮지만 수수료 대비 실효 수익이 작을 수 있습니다.",
            )
        )

    if min_position_pct > 25:
        findings.append(
            SettingsFinding(
                "warning",
                "최소 진입금 비중이 큼",
                f"최소 진입금이 총 예산의 {min_position_pct:.1f}%입니다.",
                "신호가 약한 경우에도 큰 금액이 들어갈 수 있으니 최소 진입금을 낮추세요.",
            )
        )
        suggestions["min_position_krw"] = round(risk.total_budget_krw * 0.1)

    if daily_loss_pct > 5:
        findings.append(
            SettingsFinding(
                "warning",
                "일일 손실 한도가 큼",
                f"일일 손실 한도가 총 예산의 {daily_loss_pct:.1f}%입니다.",
                "단타 초기 운영은 일일 손실 한도를 2~3% 수준으로 낮추는 편이 좋습니다.",
            )
        )
        suggestions["daily_loss_limit_krw"] = round(risk.total_budget_krw * 0.03)

    if expected_net < config.risk.min_expected_net_profit_pct:
        findings.append(
            SettingsFinding(
                "critical",
                "수수료/슬리피지 대비 기대수익 부족",
                f"익절 {risk.take_profit_pct:.2f}%에서 왕복 비용 {risk.round_trip_cost_pct:.2f}%를 빼면 기대 순수익은 {expected_net:.2f}%입니다.",
                "익절 목표를 높이거나 최소 기대 순수익 기준을 낮추기 전에 백테스트로 검증하세요.",
            )
        )
        suggestions["take_profit_pct"] = round(risk.round_trip_cost_pct + risk.min_expected_net_profit_pct + 0.2, 2)

    if reward_risk < 1.2:
        findings.append(
            SettingsFinding(
                "warning",
                "손익비가 낮음",
                f"익절/손절 비율이 {reward_risk:.2f}입니다.",
                "단타라도 손익비는 최소 1.2 이상, 가능하면 1.5 이상을 목표로 하세요.",
            )
        )

    if risk.stop_loss_pct > 1.5:
        findings.append(
            SettingsFinding(
                "warning",
                "단타 손절폭이 넓음",
                f"손절폭이 {risk.stop_loss_pct:.2f}%입니다.",
                "초기 단타는 -0.5~-1.0% 수준에서 검증하는 편이 안전합니다.",
            )
        )
        suggestions["stop_loss_pct"] = 0.8

    if risk.trailing_stop_pct > risk.take_profit_pct:
        findings.append(
            SettingsFinding(
                "warning",
                "트레일링 스탑이 익절보다 큼",
                "트레일링 스탑 폭이 익절 목표보다 커서 수익 보호가 늦을 수 있습니다.",
                "트레일링 스탑은 익절 목표보다 작게 설정하세요.",
            )
        )
        suggestions["trailing_stop_pct"] = round(max(0.3, risk.take_profit_pct * 0.5), 2)

    if interval_seconds < 15:
        findings.append(
            SettingsFinding(
                "warning",
                "반복 주기가 너무 짧음",
                f"현재 반복 주기는 {interval_seconds}초입니다.",
                "초기에는 API 제한과 과매매를 피하기 위해 30~60초 이상을 권장합니다.",
            )
        )
        suggestions["bot_interval_seconds"] = 60

    if config.scan_top_markets > 80:
        findings.append(
            SettingsFinding(
                "info",
                "스캔 종목 수가 많음",
                f"{config.scan_top_markets}개 종목을 스캔합니다.",
                "API 호출량이 늘 수 있으니 초기에는 거래대금 상위 20~40개부터 보세요.",
            )
        )
        suggestions["scan_top_markets"] = 40

    if risk.btc_crash_5m_pct > -0.5:
        findings.append(
            SettingsFinding(
                "info",
                "BTC 급락 차단 기준이 민감함",
                f"BTC 5분 변동 {risk.btc_crash_5m_pct:.2f}%에서 신규 진입을 막습니다.",
                "너무 자주 멈추면 -0.8~-1.2% 범위를 검토하세요.",
            )
        )

    if not findings:
        findings.append(
            SettingsFinding(
                "ok",
                "설정 이상 없음",
                "현재 설정은 5만원 내외 paper 단타 테스트 기준에서 큰 충돌이 없습니다.",
                "실거래 전에는 paper 로그와 백테스트 결과를 먼저 확인하세요.",
            )
        )

    safety_score = _score_findings(findings)
    mode = _mode_from_score(safety_score)
    summary = _summary(mode, safety_score, position_pct, daily_loss_pct, expected_net, reward_risk)
    return SettingsAdvice(safety_score, mode, findings, suggestions, summary)


def advice_to_dict(advice: SettingsAdvice) -> dict[str, Any]:
    return asdict(advice)


def _score_findings(findings: list[SettingsFinding]) -> int:
    score = 100
    for finding in findings:
        if finding.severity == "critical":
            score -= 25
        elif finding.severity == "warning":
            score -= 12
        elif finding.severity == "info":
            score -= 3
    return max(0, min(100, score))


def _mode_from_score(score: int) -> str:
    if score >= 85:
        return "balanced"
    if score >= 65:
        return "cautious"
    return "review_required"


def _summary(mode: str, score: int, position_pct: float, daily_loss_pct: float, expected_net: float, reward_risk: float) -> str:
    mode_label = {
        "balanced": "균형형",
        "cautious": "주의 필요",
        "review_required": "수정 필요",
    }[mode]
    return (
        f"{mode_label} 설정입니다. 안전 점수 {score}/100, "
        f"1회 진입 비중 {position_pct:.1f}%, 일일 손실 한도 {daily_loss_pct:.1f}%, "
        f"수수료 반영 기대 순수익 {expected_net:.2f}%, 손익비 {reward_risk:.2f}입니다."
    )
