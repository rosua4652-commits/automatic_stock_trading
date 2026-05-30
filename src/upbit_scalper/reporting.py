from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from .storage import read_jsonl


def build_portfolio_report(
    snapshots_path: str = "logs/portfolio.jsonl",
    output_path: str = "reports/portfolio.html",
) -> Path:
    rows = read_jsonl(snapshots_path)
    values = [_extract_total_value(row) for row in rows]
    values = [value for value in values if value is not None]

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    latest = rows[-1] if rows else {}
    html = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>자금 현황 리포트</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #17202a; }}
    .metric {{ display: inline-block; margin: 0 20px 20px 0; padding: 16px; background: #f4f6f7; border-radius: 8px; }}
    svg {{ width: 100%; max-width: 900px; height: 280px; border: 1px solid #d5dbdb; background: #fff; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
    th, td {{ border-bottom: 1px solid #e5e8e8; padding: 8px; text-align: right; }}
    th:first-child, td:first-child {{ text-align: left; }}
  </style>
</head>
<body>
  <h1>자금 현황 리포트</h1>
  <div class="metric"><strong>저장된 스냅샷</strong><br>{len(rows)}</div>
  <div class="metric"><strong>최근 평가금액</strong><br>{_fmt_krw(values[-1]) if values else "N/A"}</div>
  <div class="metric"><strong>전체 변동</strong><br>{_fmt_change(values)}</div>
  <h2>자산 변동 그래프</h2>
  {_sparkline_svg(values)}
  <h2>최근 자산 비중</h2>
  {_allocation_table(latest)}
</body>
</html>
"""
    target.write_text(html, encoding="utf-8")
    return target


def _extract_total_value(row: dict[str, Any]) -> float | None:
    snapshot = row.get("snapshot", row)
    value = snapshot.get("total_value_krw") if isinstance(snapshot, dict) else None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sparkline_svg(values: list[float]) -> str:
    if not values:
        return "<p>아직 저장된 자금 스냅샷이 없습니다.</p>"
    width = 900
    height = 260
    padding = 20
    minimum = min(values)
    maximum = max(values)
    span = maximum - minimum or 1

    points = []
    for index, value in enumerate(values):
        x = padding + (index / max(1, len(values) - 1)) * (width - padding * 2)
        y = height - padding - ((value - minimum) / span) * (height - padding * 2)
        points.append(f"{x:.2f},{y:.2f}")

    return (
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="portfolio equity curve">'
        f'<polyline fill="none" stroke="#2874a6" stroke-width="3" points="{" ".join(points)}" />'
        f'<text x="{padding}" y="{height - 4}" font-size="12">{_fmt_krw(minimum)}</text>'
        f'<text x="{padding}" y="14" font-size="12">{_fmt_krw(maximum)}</text>'
        "</svg>"
    )


def _allocation_table(row: dict[str, Any]) -> str:
    snapshot = row.get("snapshot", row)
    assets = snapshot.get("assets", []) if isinstance(snapshot, dict) else []
    if not assets:
        return "<p>아직 자산 비중 데이터가 없습니다.</p>"
    body = []
    for asset in assets:
        body.append(
            "<tr>"
            f"<td>{escape(str(asset.get('currency', '')))}</td>"
            f"<td>{float(asset.get('value_krw', 0)):,.0f}</td>"
            f"<td>{float(asset.get('allocation_pct', 0)):.2f}%</td>"
            f"<td>{float(asset.get('unrealized_pnl_krw', 0)):,.0f}</td>"
            f"<td>{float(asset.get('unrealized_pnl_pct', 0)):.2f}%</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>자산</th><th>평가금액(KRW)</th><th>비중</th>"
        "<th>미실현 손익</th><th>미실현 수익률</th></tr></thead>"
        f"<tbody>{''.join(body)}</tbody></table>"
    )


def _fmt_krw(value: float) -> str:
    return f"{value:,.0f} KRW"


def _fmt_change(values: list[float]) -> str:
    if len(values) < 2:
        return "N/A"
    change = values[-1] - values[0]
    pct = (change / values[0] * 100) if values[0] else 0
    return f"{change:,.0f} KRW ({pct:.2f}%)"
