import { useCallback, useEffect, useMemo, useState } from "react";
import type { AppConfig, InvestmentRecommendation } from "../types";
import {
  balanceRecommendationAmounts,
  computeTradePlan,
  deployableCashKrw,
  MIN_BUY_KRW,
} from "../utils";

export type EditableRecommendation = InvestmentRecommendation & {
  amount_krw: number;
  quantity_est: number;
  stop_loss_price_usdt: number;
  take_profit_price_usdt: number;
  stop_loss_krw: number;
  take_profit_krw: number;
};

export type ApplyItem = { symbol: string; amount_krw: number };

function enrich(
  r: InvestmentRecommendation,
  amount: number,
  config: AppConfig,
  usdtKrw: number
): EditableRecommendation {
  const plan = computeTradePlan(
    amount,
    r.price_usdt ?? 0,
    usdtKrw,
    config.stop_loss_pct,
    config.take_profit_pct
  );
  return {
    ...r,
    amount_krw: amount,
    quantity_est: plan.quantity_est,
    stop_loss_price_usdt: plan.stop_loss_price_usdt,
    take_profit_price_usdt: plan.take_profit_price_usdt,
    stop_loss_krw: plan.stop_loss_krw,
    take_profit_krw: plan.take_profit_krw,
  };
}

export function useRecommendationAmounts(
  recommendations: InvestmentRecommendation[],
  config: AppConfig,
  cashKrw: number,
  usdtKrw = 1350
) {
  const feePct = config.trading_fee_pct ?? 0.05;
  const budget = deployableCashKrw(cashKrw, feePct);

  const balancedBase = useMemo(
    () => balanceRecommendationAmounts(recommendations, cashKrw, feePct),
    [recommendations, cashKrw, feePct]
  );

  const recKey = useMemo(
    () =>
      recommendations
        .map((r) => `${r.symbol}:${r.amount_krw}:${r.selected}`)
        .join("|"),
    [recommendations]
  );

  const [amounts, setAmounts] = useState<Record<string, number>>({});
  const [syncKey, setSyncKey] = useState("");

  useEffect(() => {
    if (recKey === syncKey) return;
    setSyncKey(recKey);
    setAmounts(balancedBase);
  }, [recKey, syncKey, balancedBase]);

  const list: EditableRecommendation[] = useMemo(() => {
    const merged = recommendations.map((r) => {
      const raw = amounts[r.symbol] ?? balancedBase[r.symbol] ?? r.amount_krw;
      const amt = Math.max(
        MIN_BUY_KRW,
        Math.round(raw / 1000) * 1000
      );
      return enrich(r, amt, config, usdtKrw);
    });

    const total = merged.reduce((s, r) => s + (r.selected !== false ? r.amount_krw : 0), 0);
    if (total <= budget || total === 0) return merged;

    const scaled = balanceRecommendationAmounts(
      merged.map((r) => ({
        symbol: r.symbol,
        amount_krw: r.amount_krw,
        selected: r.selected,
      })),
      cashKrw,
      feePct
    );
    return merged
      .map((r) => {
        const amt = scaled[r.symbol] ?? r.amount_krw;
        return enrich(r, amt >= MIN_BUY_KRW ? amt : 0, config, usdtKrw);
      })
      .filter((r) => r.amount_krw >= MIN_BUY_KRW);
  }, [recommendations, amounts, balancedBase, config, usdtKrw, cashKrw, feePct, budget]);

  const totalSelected = useMemo(
    () =>
      list
        .filter((r) => r.selected !== false)
        .reduce((s, r) => s + r.amount_krw, 0),
    [list]
  );

  const setAmount = useCallback(
    (symbol: string, amount: number) => {
      setAmounts((prev) => {
        const next = {
          ...prev,
          [symbol]: Math.max(MIN_BUY_KRW, Math.round(amount / 1000) * 1000),
        };
        const draft = recommendations.map((r) => ({
          symbol: r.symbol,
          amount_krw: next[r.symbol] ?? prev[r.symbol] ?? r.amount_krw,
          selected: r.selected,
        }));
        return balanceRecommendationAmounts(draft, cashKrw, feePct);
      });
    },
    [recommendations, cashKrw, feePct]
  );

  const resetToAi = useCallback(
    (symbol: string) => {
      const v = balancedBase[symbol];
      if (v) setAmounts((prev) => ({ ...prev, [symbol]: v }));
    },
    [balancedBase]
  );

  const resetAllToAi = useCallback(() => {
    setAmounts({ ...balancedBase });
  }, [balancedBase]);

  const getApplyItems = useCallback(
    (symbols: string[]): ApplyItem[] => {
      const items = symbols
        .map((sym) => {
          const row = list.find((r) => r.symbol === sym);
          return {
            symbol: sym,
            amount_krw: row?.amount_krw ?? amounts[sym] ?? MIN_BUY_KRW,
          };
        })
        .filter((i) => i.amount_krw >= MIN_BUY_KRW);
      const scaled = balanceRecommendationAmounts(
        items.map((i) => ({
          symbol: i.symbol,
          amount_krw: i.amount_krw,
          selected: true,
        })),
        cashKrw,
        feePct
      );
      return symbols
        .filter((sym) => scaled[sym] >= MIN_BUY_KRW)
        .map((sym) => ({ symbol: sym, amount_krw: scaled[sym] }));
    },
    [list, amounts, cashKrw, feePct]
  );

  const aiAmounts = useMemo(() => ({ ...balancedBase }), [balancedBase]);

  return {
    list,
    aiAmounts,
    totalSelected,
    deployableBudget: budget,
    setAmount,
    resetToAi,
    resetAllToAi,
    getApplyItems,
  };
}
