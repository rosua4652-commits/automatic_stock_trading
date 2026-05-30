import { useCallback, useEffect, useMemo, useState } from "react";
import type { AppConfig, InvestmentRecommendation } from "../types";
import { computeTradePlan, MIN_BUY_KRW } from "../utils";

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
  usdtKrw = 1350
) {
  const [amounts, setAmounts] = useState<Record<string, number>>({});

  useEffect(() => {
    setAmounts((prev) => {
      const next = { ...prev };
      for (const r of recommendations) {
        if (next[r.symbol] === undefined) {
          next[r.symbol] = r.amount_krw;
        }
      }
      return next;
    });
  }, [recommendations]);

  const list: EditableRecommendation[] = useMemo(() => {
    return recommendations.map((r) => {
      const amt = Math.max(
        MIN_BUY_KRW,
        Math.round((amounts[r.symbol] ?? r.amount_krw) / 1000) * 1000
      );
      return enrich(r, amt, config, usdtKrw);
    });
  }, [recommendations, amounts, config, usdtKrw]);

  const setAmount = useCallback((symbol: string, amount: number) => {
    setAmounts((prev) => ({ ...prev, [symbol]: amount }));
  }, []);

  const resetToAi = useCallback(
    (symbol: string) => {
      const r = recommendations.find((x) => x.symbol === symbol);
      if (r) setAmount(symbol, r.amount_krw);
    },
    [recommendations, setAmount]
  );

  const resetAllToAi = useCallback(() => {
    const m: Record<string, number> = {};
    recommendations.forEach((r) => {
      m[r.symbol] = r.amount_krw;
    });
    setAmounts(m);
  }, [recommendations]);

  const getApplyItems = useCallback(
    (symbols: string[]): ApplyItem[] => {
      return symbols.map((sym) => {
        const row = list.find((r) => r.symbol === sym);
        return {
          symbol: sym,
          amount_krw: row?.amount_krw ?? amounts[sym] ?? MIN_BUY_KRW,
        };
      });
    },
    [list, amounts]
  );

  const aiAmounts = useMemo(() => {
    const m: Record<string, number> = {};
    recommendations.forEach((r) => {
      m[r.symbol] = r.amount_krw;
    });
    return m;
  }, [recommendations]);

  return {
    list,
    aiAmounts,
    setAmount,
    resetToAi,
    resetAllToAi,
    getApplyItems,
  };
}
