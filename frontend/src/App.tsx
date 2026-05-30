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
import SettingsModal from "./components/SettingsModal";
import type { AppConfig, Candle, StatusPayload } from "./types";
import { DEFAULT_CONFIG, fmtKrw, isRunning, mergeWsPayload } from "./utils";

export default function App() {
  const [data, setData] = useState<StatusPayload | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [configDraft, setConfigDraft] = useState<AppConfig>(DEFAULT_CONFIG);
  const [chartInterval, setChartInterval] = useState("1h");
  const [activeSymbol, setActiveSymbol] = useState("BTCUSDT");
  const [candles, setCandles] = useState<Candle[]>([]);
  const [chartLoading, setChartLoading] = useState(false);
  const [chartError, setChartError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [botBusy, setBotBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const botLockVersionRef = useRef(0);
  const activeSymbolRef = useRef(activeSymbol);
  activeSymbolRef.current = activeSymbol;

  const applyPayload = useCallback((incoming: StatusPayload, lockBot = false) => {
    setData((prev) => {
      const base = prev && lockBot
        ? mergeWsPayload(prev, incoming, botLockVersionRef.current)
        : incoming;
      return base;
    });
    // 서버 view_symbol은 탭 클릭 시에만 동기화 — WS로 activeSymbol 덮지 않음
  }, []);

  useEffect(() => {
    fetchStatus()
      .then((s) => {
        applyPayload(s);
        setActiveSymbol(s.bot.view_symbol || "BTCUSDT");
        setConfigDraft(s.config);
      })
      .catch((e) => setToast(String(e)))
      .finally(() => setLoading(false));

    return connectWs((msg) => {
      setData((prev) => {
        if (!prev) return msg;
        return mergeWsPayload(prev, msg, botLockVersionRef.current);
      });
    });
  }, [applyPayload]);

  // 차트 로드 — setInterval 이름 충돌 수정 (window.setInterval 사용)
  useEffect(() => {
    let cancelled = false;
    const sym = activeSymbol;

    const load = async () => {
      setChartLoading(true);
      setChartError(null);
      try {
        const res = await fetchChart(sym, chartInterval);
        if (!cancelled && activeSymbolRef.current === sym) {
          setCandles(res.candles || []);
        }
      } catch (e) {
        if (!cancelled && activeSymbolRef.current === sym) {
          setCandles([]);
          setChartError(e instanceof Error ? e.message : "차트 로드 실패");
        }
      } finally {
        if (!cancelled) setChartLoading(false);
      }
    };

    load();
    const timerId = window.setInterval(load, 12000);
    return () => {
      cancelled = true;
      window.clearInterval(timerId);
    };
  }, [activeSymbol, chartInterval]);

  const handleSelectCoin = useCallback(
    async (sym: string) => {
      setActiveSymbol(sym);
      setCandles([]);
      setChartError(null);
      try {
        const status = await setViewSymbol(sym);
        applyPayload(status);
        // view 객체를 선택한 코인으로 맞춤
        if (status.view?.meta?.symbol === sym) {
          setData(status);
        }
      } catch (e) {
        setToast(e instanceof Error ? e.message : "코인 전환 실패");
      }
    },
    [applyPayload]
  );

  const toggleBot = async () => {
    if (botBusy || !data) return;
    setBotBusy(true);
    botLockVersionRef.current = (data.status_version ?? 0) + 1000;

    try {
      if (isRunning(data.bot.status)) {
        setData({
          ...data,
          bot: { ...data.bot, status: "stopping", message: "중지 요청 중..." },
        });
        const s = await stopBot();
        botLockVersionRef.current = s.status_version ?? botLockVersionRef.current;
        setData(s);
        showToast("자동투자가 중지되었습니다");
      } else {
        setData({
          ...data,
          bot: { ...data.bot, status: "running", message: "시작 중..." },
        });
        const s = await startBot();
        botLockVersionRef.current = s.status_version ?? botLockVersionRef.current;
        setData(s);
        if (s.ok === false) {
          showToast(s.message || "시작할 수 없습니다");
        } else {
          showToast("자동투자를 시작했습니다");
        }
      }
    } catch (e) {
      showToast(e instanceof Error ? e.message : "요청 실패");
      const s = await fetchStatus();
      applyPayload(s);
    } finally {
      setBotBusy(false);
    }
  };

  const showToast = (msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast(null), 3500);
  };

  const handleSaveSettings = async () => {
    setSaving(true);
    try {
      const s = await saveConfig(configDraft);
      applyPayload(s);
      setSettingsOpen(false);
      showToast("설정이 저장되었습니다");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "저장 실패");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="app loading-screen">
        <div className="loader" />
        <p>AIDI 로딩 중</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="app loading-screen">
        <p>서버 연결 실패</p>
        <button type="button" className="btn-primary" onClick={() => location.reload()}>
          새로고침
        </button>
      </div>
    );
  }

  const running = isRunning(data.bot.status);
  const stopping = data.bot.status === "stopping";
  const isPaper = data.config.trade_mode === "paper";
  const tabs =
    data.tabs?.length > 0
      ? data.tabs
      : [
          activeSymbol,
          ...data.portfolio.positions.map((p) => p.symbol),
        ];

  const view =
    data.view?.meta?.symbol === activeSymbol
      ? data.view
      : (() => {
          const pos = data.portfolio.positions.find((p) => p.symbol === activeSymbol);
          const cand = data.bot.candidates.find((c) => c.symbol === activeSymbol);
          const base = activeSymbol.replace("USDT", "");
          const meta = pos
            ? {
                symbol: pos.symbol,
                base: pos.base,
                quote: "USDT",
                name_ko: pos.name_ko,
                name_en: pos.name_en,
                pair_label: pos.pair_label,
                display: pos.display,
              }
            : cand
              ? {
                  symbol: cand.symbol,
                  base: cand.base,
                  quote: "USDT",
                  name_ko: cand.name_ko,
                  name_en: cand.name_en,
                  pair_label: cand.pair_label,
                  display: cand.display,
                }
              : {
                  symbol: activeSymbol,
                  base,
                  quote: "USDT",
                  name_ko: base,
                  name_en: base,
                  pair_label: `${base}/USDT`,
                  display: `${base} (${base})`,
                };
          return {
            meta,
            price_usdt: pos?.current_price ?? 0,
            change_24h: cand?.change_24h ?? 0,
            in_portfolio: !!pos,
            position: pos ?? null,
            candidate: cand ?? null,
          };
        })();

  const pairLabel =
    data.portfolio.positions.find((p) => p.symbol === activeSymbol)?.pair_label ||
    data.bot.candidates.find((c) => c.symbol === activeSymbol)?.pair_label ||
    `${activeSymbol.replace("USDT", "")}/USDT`;

  return (
    <div className="app">
      <div className={`mode-banner ${isPaper ? "paper" : "live"}`}>
        {isPaper ? "모의투자 모드 — 실제 주문 없음" : "실거래 모드 — 실제 자금 사용"}
      </div>

      <header className="topbar">
        <div className="brand">
          <span className="logo">AIDI</span>
          <span className="tagline">AI 자동투자</span>
        </div>
        <div className="top-actions">
          <button
            type="button"
            className="btn-ghost"
            onClick={() => {
              setConfigDraft(data.config);
              setSettingsOpen(true);
            }}
          >
            설정
          </button>
          <button
            type="button"
            className={`btn-primary ${running || stopping ? "stop" : ""}`}
            onClick={toggleBot}
            disabled={botBusy || stopping}
          >
            {stopping ? "중지 중..." : running ? "자동투자 중지" : "자동투자 시작"}
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
          <span className="m-value accent">{data.portfolio.progress_pct.toFixed(0)}%</span>
        </div>
        <div className="metric">
          <span className="m-label">총 자산</span>
          <span className="m-value">{fmtKrw(data.portfolio.total_value_krw)}원</span>
        </div>
      </div>

      <CoinTabs
        tabs={tabs}
        selected={activeSymbol}
        portfolio={data.portfolio}
        candidates={data.bot.candidates}
        onSelect={handleSelectCoin}
      />

      <CoinDetailBar
        view={view}
        botStatus={data.bot.status}
        botMessage={data.bot.message}
      />

      <main className="layout">
        <PortfolioPanel
          portfolio={data.portfolio}
          candidates={data.bot.candidates}
          trades={data.bot.recent_trades}
          selected={activeSymbol}
          onSelect={handleSelectCoin}
        />
        <ChartPanel
          symbol={activeSymbol}
          pairLabel={pairLabel}
          chartInterval={chartInterval}
          candles={candles}
          chartLoading={chartLoading}
          chartError={chartError}
          onIntervalChange={setChartInterval}
        />
      </main>

      {toast && <div className="toast">{toast}</div>}

      {settingsOpen && (
        <SettingsModal
          config={data.config}
          draft={configDraft}
          onChange={setConfigDraft}
          onSave={handleSaveSettings}
          onClose={() => setSettingsOpen(false)}
          saving={saving}
        />
      )}
    </div>
  );
}
