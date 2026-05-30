import { useCallback, useEffect, useState } from "react";
import {
  connectWs,
  fetchChart,
  fetchStatus,
  saveConfig,
  selectSymbol,
  startBot,
  stopBot,
} from "./api";
import ChartPanel from "./components/ChartPanel";
import PortfolioPanel from "./components/PortfolioPanel";
import type { Candle, StatusPayload } from "./types";

function fmt(n: number) {
  return new Intl.NumberFormat("ko-KR").format(Math.round(n));
}

export default function App() {
  const [data, setData] = useState<StatusPayload | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [targetInput, setTargetInput] = useState("2000000");
  const [interval, setInterval] = useState("1h");
  const [candles, setCandles] = useState<Candle[]>([]);
  const [loading, setLoading] = useState(true);

  const symbol = data?.bot.selected_symbol ?? "BTCUSDT";
  const running = data?.bot.status === "running";

  useEffect(() => {
    fetchStatus()
      .then((s) => {
        setData(s);
        setTargetInput(String(s.config.target_profit_krw));
      })
      .finally(() => setLoading(false));
    return connectWs(setData);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const c = await fetchChart(symbol, interval);
        if (!cancelled) setCandles(c);
      } catch {
        /* retry next tick */
      }
    };
    load();
    const t = setInterval(load, 15000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [symbol, interval]);

  const handleSelect = useCallback(async (sym: string) => {
    await selectSymbol(sym);
    setData((prev) =>
      prev ? { ...prev, bot: { ...prev.bot, selected_symbol: sym } } : prev
    );
  }, []);

  const toggleBot = async () => {
    if (running) await stopBot();
    else await startBot();
    const s = await fetchStatus();
    setData(s);
  };

  const applySettings = async () => {
    const target = Math.max(100000, Number(targetInput.replace(/,/g, "")) || 0);
    await saveConfig({ target_profit_krw: target });
    setSettingsOpen(false);
    const s = await fetchStatus();
    setData(s);
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

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">AIDI</span>
          <span className="tagline">AI 자동투자</span>
        </div>

        <div className="top-center">
          <div className={`status-pill ${running ? "on" : ""}`}>
            <span className="dot" />
            {running ? "자동투자 실행 중" : "대기"}
          </div>
          {running && <span className="bot-msg">{data.bot.message}</span>}
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
            className={`btn-primary ${running ? "stop" : ""}`}
            onClick={toggleBot}
          >
            {running ? "자동투자 중지" : "자동투자 시작"}
          </button>
        </div>
      </header>

      <div className="hero-metrics">
        <div className="metric">
          <span className="m-label">목표 수익</span>
          <span className="m-value">{fmt(data.config.target_profit_krw)}원</span>
        </div>
        <div className="metric">
          <span className="m-label">달성</span>
          <span className="m-value accent">
            {data.portfolio.progress_pct.toFixed(0)}%
          </span>
        </div>
        <div className="metric">
          <span className="m-label">총 자산</span>
          <span className="m-value">{fmt(data.portfolio.total_value_krw)}원</span>
        </div>
      </div>

      <main className="layout">
        <PortfolioPanel
          portfolio={data.portfolio}
          candidates={data.bot.candidates}
          trades={data.bot.recent_trades}
          selected={symbol}
          onSelect={handleSelect}
        />
        <ChartPanel
          symbol={symbol}
          interval={interval}
          candles={candles}
          onIntervalChange={setInterval}
        />
      </main>

      <footer className="disclaimer">
        모의투자(Paper) 모드 · 실제 거래 없음 · 익절·손절 AI 자동 처리
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
            aria-labelledby="settings-title"
          >
            <h2 id="settings-title">설정</h2>
            <p className="modal-desc">목표 수익 금액만 설정하세요. 나머지는 AI가 처리합니다.</p>
            <label className="field">
              <span>목표 수익 (원)</span>
              <input
                type="text"
                inputMode="numeric"
                value={targetInput}
                onChange={(e) => setTargetInput(e.target.value)}
                placeholder="예: 2000000"
              />
            </label>
            <div className="modal-actions">
              <button type="button" className="btn-ghost" onClick={() => setSettingsOpen(false)}>
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
