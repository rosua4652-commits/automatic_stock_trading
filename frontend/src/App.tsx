import { useCallback, useEffect, useRef, useState } from "react";
import {
  connectWs,
  fetchChart,
  fetchStatus,
  saveConfig,
  setViewSymbol,
  startBot,
  stopBot,
} from "./api";
import ChartPanel from "./components/ChartPanel";
import CoinDetailBar from "./components/CoinDetailBar";
import CoinTabs from "./components/CoinTabs";
import PortfolioPanel from "./components/PortfolioPanel";
import type { Candle, StatusPayload } from "./types";
import { fmtKrw, isRunning, mergeStatus } from "./utils";

export default function App() {
  const [data, setData] = useState<StatusPayload | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [targetInput, setTargetInput] = useState("2000000");
  const [interval, setInterval] = useState("1h");
  const [candles, setCandles] = useState<Candle[]>([]);
  const [chartLoading, setChartLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [botBusy, setBotBusy] = useState(false);

  const viewSymbol = data?.bot.view_symbol ?? "BTCUSDT";
  const viewLockRef = useRef<string | null>(null);
  const running = data ? isRunning(data.bot.status) : false;
  const stopping = data?.bot.status === "stopping";

  const applyStatus = useCallback((payload: StatusPayload) => {
    setData((prev) => mergeStatus(prev, payload, viewLockRef.current));
  }, []);

  useEffect(() => {
    fetchStatus()
      .then((s) => {
        applyStatus(s);
        setTargetInput(String(s.config.target_profit_krw));
      })
      .finally(() => setLoading(false));
    return connectWs(applyStatus);
  }, [applyStatus]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setChartLoading(true);
      try {
        const c = await fetchChart(viewSymbol, interval);
        if (!cancelled) setCandles(c);
      } catch {
        if (!cancelled) setCandles([]);
      } finally {
        if (!cancelled) setChartLoading(false);
      }
    };
    load();
    const t = setInterval(load, 12000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [viewSymbol, interval]);

  const handleSelect = useCallback(
    async (sym: string) => {
      viewLockRef.current = sym;
      setChartLoading(true);
      setCandles([]);
      try {
        const status = await setViewSymbol(sym);
        applyStatus(status);
      } catch {
        setData((prev) =>
          prev
            ? {
                ...prev,
                bot: { ...prev.bot, view_symbol: sym },
              }
            : prev
        );
      }
      setTimeout(() => {
        viewLockRef.current = null;
      }, 3000);
    },
    [applyStatus]
  );

  const toggleBot = async () => {
    if (botBusy) return;
    setBotBusy(true);
    try {
      if (running || stopping) {
        setData((prev) =>
          prev
            ? {
                ...prev,
                bot: {
                  ...prev.bot,
                  status: "stopping",
                  message: "중지 요청 처리 중...",
                },
              }
            : prev
        );
        const s = await stopBot();
        applyStatus(s);
      } else {
        const s = await startBot();
        applyStatus(s);
      }
    } catch (e) {
      console.error(e);
      const s = await fetchStatus();
      applyStatus(s);
    } finally {
      setBotBusy(false);
    }
  };

  const applySettings = async () => {
    const target = Math.max(
      100000,
      Number(targetInput.replace(/,/g, "")) || 0
    );
    const s = await saveConfig({ target_profit_krw: target });
    applyStatus(s);
    setSettingsOpen(false);
  };

  if (loading) {
    return (
      <div className="app loading-screen">
        <div className="loader" />
        <p>AIDI 로딩 중</p>
      </div>
    );
  }

  if (!data) return null;

  const tabs =
    data.tabs?.length > 0
      ? data.tabs
      : [viewSymbol, ...data.portfolio.positions.map((p) => p.symbol)];

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">AIDI</span>
          <span className="tagline">AI 자동투자</span>
        </div>
        <div className="top-actions">
          <button
            type="button"
            className="btn-ghost"
            onClick={() => setSettingsOpen(true)}
            aria-label="설정"
          >
            ⚙
          </button>
          <button
            type="button"
            className={`btn-primary ${running || stopping ? "stop" : ""}`}
            onClick={toggleBot}
            disabled={botBusy || stopping}
          >
            {stopping
              ? "중지 중..."
              : running
                ? "자동투자 중지"
                : "자동투자 시작"}
          </button>
        </div>
      </header>

      <div className="hero-metrics">
        <div className="metric">
          <span className="m-label">목표 수익</span>
          <span className="m-value">{fmtKrw(data.config.target_profit_krw)}원</span>
        </div>
        <div className="metric">
          <span className="m-label">달성</span>
          <span className="m-value accent">
            {data.portfolio.progress_pct.toFixed(0)}%
          </span>
        </div>
        <div className="metric">
          <span className="m-label">총 자산</span>
          <span className="m-value">
            {fmtKrw(data.portfolio.total_value_krw)}원
          </span>
        </div>
      </div>

      <CoinTabs
        tabs={tabs}
        selected={viewSymbol}
        portfolio={data.portfolio}
        candidates={data.bot.candidates}
        onSelect={handleSelect}
      />

      <CoinDetailBar
        view={data.view}
        botStatus={data.bot.status}
        botMessage={data.bot.message}
      />

      <main className="layout">
        <PortfolioPanel
          portfolio={data.portfolio}
          candidates={data.bot.candidates}
          trades={data.bot.recent_trades}
          selected={viewSymbol}
          onSelect={handleSelect}
        />
        <ChartPanel
          symbol={viewSymbol}
          pairLabel={data.view.meta.pair_label}
          interval={interval}
          candles={candles}
          chartLoading={chartLoading}
          onIntervalChange={setInterval}
        />
      </main>

      <footer className="disclaimer">
        모의투자(Paper) · 실제 주문 없음 · 익절·손절 AI 자동
      </footer>

      {settingsOpen && (
        <div
          className="modal-backdrop"
          onClick={() => setSettingsOpen(false)}
          role="presentation"
        >
          <div
            className="modal"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
          >
            <h2>설정</h2>
            <p className="modal-desc">
              목표 수익만 설정하세요. 매매·익절·손절은 AI가 처리합니다.
            </p>
            <label className="field">
              <span>목표 수익 (원)</span>
              <input
                type="text"
                inputMode="numeric"
                value={targetInput}
                onChange={(e) => setTargetInput(e.target.value)}
              />
            </label>
            <div className="modal-actions">
              <button
                type="button"
                className="btn-ghost wide"
                onClick={() => setSettingsOpen(false)}
              >
                취소
              </button>
              <button type="button" className="btn-primary" onClick={applySettings}>
                저장
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
