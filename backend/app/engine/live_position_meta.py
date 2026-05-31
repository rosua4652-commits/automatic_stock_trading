"""실거래 포지션 메타 — AIDI 매수·동기화 시 진입 유형(롱/단타) 유지."""

from __future__ import annotations

import time
from typing import Any

def _as_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return dict(item)
    if hasattr(item, "model_dump"):
        return dict(item.model_dump())
    return {}


def outlook_from_reason_text(reason: str) -> str:
    """주문/체결 사유 문자열 → 보유 카드용 진입 유형."""
    t = (reason or "").strip()
    low = t.lower()
    if "단타" in t or "scalp" in low:
        return "AI 단타 자동"
    if "롱" in t or "long" in low:
        return "AI 롱 자동"
    if "자동투자" in t or "ai 자동" in low or "승인" in t:
        return "AI 롱 자동"
    if "ai" in low and ("매수" in t or "투자" in t):
        return "AI 롱 자동"
    return ""


def entry_mode_label(outlook: str) -> str:
    o = (outlook or "").strip()
    if "단타" in o:
        return "단타"
    if "롱" in o:
        return "롱"
    if o:
        return "AI"
    return ""


def _full_buy_reason(live_meta: dict[str, Any], trade_row: dict[str, Any]) -> str:
    from app.engine.trade_history import collect_reason_hints

    uid = str(trade_row.get("order_uuid") or "").strip()
    hints = collect_reason_hints(live_meta)
    if uid and uid in hints:
        return str(hints[uid].get("reason") or trade_row.get("reason") or "")
    return str(trade_row.get("reason") or "")


def infer_recent_aidi_buy(
    live_meta: dict[str, Any], symbol: str
) -> dict[str, Any] | None:
    """해당 종목 최근 AIDI 매수 메타 (동기화 유실 복구용)."""
    sym = symbol.upper()
    best_ts = 0.0
    best: dict[str, Any] | None = None

    for raw in live_meta.get("trades") or []:
        d = _as_dict(raw)
        if str(d.get("symbol") or "").upper() != sym:
            continue
        if str(d.get("side") or "").upper() != "BUY":
            continue
        full = _full_buy_reason(live_meta, d)
        is_auto = bool(d.get("is_auto"))
        if not is_auto and "승인" not in full and "ai" not in full.lower():
            continue
        outlook = outlook_from_reason_text(full)
        if not outlook and not is_auto:
            continue
        ts = float(d.get("ts") or 0)
        if ts < best_ts:
            continue
        best_ts = ts
        best = {
            "entry_outlook": outlook or "AI 롱 자동",
            "entry_reason": full[:280] if full else "AIDI 자동 매수",
            "is_auto": True,
            "amount_krw": float(d.get("amount_krw") or 0),
        }
    return best


def patch_position_meta_for_buy(
    live_meta: dict[str, Any],
    symbol: str,
    *,
    add_qty: float,
    amount_krw: float,
    entry_outlook: str,
    entry_reason: str,
    as_auto: bool,
) -> None:
    """체결 직후·동기화 전에 positions_meta 선반영 (유실 방지)."""
    sym = symbol.upper()
    bag = live_meta.setdefault("positions_meta", {})
    pm: dict[str, Any] = dict(bag.get(sym) or {})
    outlook = (entry_outlook or "").strip() or outlook_from_reason_text(
        entry_reason
    )
    if as_auto:
        prev_auto = float(pm.get("auto_quantity") or 0)
        pm["auto_quantity"] = prev_auto + max(0.0, add_qty)
        pm["auto_cost_basis_krw"] = float(pm.get("auto_cost_basis_krw") or 0) + max(
            0.0, amount_krw
        )
        pm["excluded_from_auto"] = False
        if outlook:
            pm["entry_outlook"] = outlook
        if entry_reason:
            pm["entry_reason"] = entry_reason
        elif not pm.get("entry_reason"):
            pm["entry_reason"] = outlook or "AIDI 자동 매수"
        if float(pm.get("entry_score") or 0) <= 0:
            pass
        pm.setdefault("opened_at", time.time())
    else:
        prev_man = float(pm.get("manual_quantity") or 0)
        pm["manual_quantity"] = prev_man + max(0.0, add_qty)
        pm["manual_cost_basis_krw"] = float(pm.get("manual_cost_basis_krw") or 0) + max(
            0.0, amount_krw
        )
        if entry_reason:
            pm["entry_reason"] = entry_reason
    bag[sym] = pm


def heal_position_meta(
    pm: dict[str, Any],
    symbol: str,
    live_meta: dict[str, Any],
    *,
    total_qty: float,
) -> dict[str, Any]:
    """
    업비트 동기화 시 — order_reasons/체결 이력으로 롱·AI 수량 복구.
    """
    out = dict(pm or {})
    if total_qty <= 1e-12:
        return out

    inferred = infer_recent_aidi_buy(live_meta, symbol)
    outlook = str(out.get("entry_outlook") or "").strip()
    if not outlook and inferred:
        outlook = str(inferred.get("entry_outlook") or "")
        if outlook:
            out["entry_outlook"] = outlook

    reason = str(out.get("entry_reason") or "").strip()
    if (not reason or reason in ("업비트 동기화", "거래소 동기화")) and inferred:
        out["entry_reason"] = str(inferred.get("entry_reason") or reason)

    auto_q = float(out.get("auto_quantity") or 0)
    excluded = bool(out.get("excluded_from_auto"))
    if (
        inferred
        and inferred.get("is_auto")
        and not excluded
        and auto_q <= 1e-12
    ):
        out["auto_quantity"] = total_qty
        out["manual_quantity"] = 0.0
        amt = float(inferred.get("amount_krw") or 0)
        if amt > 0:
            out["auto_cost_basis_krw"] = amt
        auto_q = total_qty

    if excluded:
        out["manual_quantity"] = total_qty
        out["auto_quantity"] = 0.0
    elif auto_q > total_qty:
        out["auto_quantity"] = total_qty
        out["manual_quantity"] = 0.0
    else:
        man = float(out.get("manual_quantity") or 0)
        if man <= 0 or abs(auto_q + man - total_qty) > 1e-6:
            out["manual_quantity"] = max(0.0, total_qty - auto_q)

    return out


def default_entry_reason(pm: dict[str, Any], symbol: str, live_meta: dict[str, Any]) -> str:
    r = str(pm.get("entry_reason") or "").strip()
    if r and r not in ("업비트 동기화", "거래소 동기화"):
        return r
    inferred = infer_recent_aidi_buy(live_meta, symbol)
    if inferred and inferred.get("entry_reason"):
        return str(inferred["entry_reason"])
    return "업비트 동기화"
