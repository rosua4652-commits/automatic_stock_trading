import { useCallback, useEffect, useRef, useState } from "react";
import {
  applyRecommendations,
  connectWs,
  fetchChart,
  fetchStatus,
  manualBuy,
  manualSell,
  sellAll,
  saveConfig,
  scanDirectionSignals,
  setPositionExclude,
  setPositionExitPlan,
  setViewSymbol,
  resetRiskKill,
  migratePositionExits,
  setAutoBuyPaused,
  startBot,
  stopBot,
} from "./api";
import ActivityPanel from "./components/ActivityPanel";
import AlertsHub from "./components/AlertsHub";
import RecommendationsPanel from "./components/RecommendationsPanel";
import ChartPanel from "./components/ChartPanel";
import CoinDetailBar from "./components/CoinDetailBar";
import CoinSearchTabs from "./components/CoinSearchTabs";
import FundsSummaryStrip from "./components/FundsSummaryStrip";
import FundsTab from "./components/FundsTab";
import StatsTab from "./components/StatsTab";
import PortfolioAllocationPanel from "./components/PortfolioAllocationPanel";
import PortfolioPanel from "./components/PortfolioPanel";
import SettingsModal from "./components/SettingsModal";
import type {
  AppConfig,
  Candle,
  ChartMarkerDto,
  ChartTradeLevels,
  MainView,
  StatusPayload,
} from "./types";
import { useRecommendationAmounts } from "./hooks/useRecommendationAmounts";
import type { ApplyItem } from "./hooks/useRecommendationAmounts";
import {
  isBuildGenerationCompatible,
  isServerBuildNewEnough,
  REQUIRED_BUILD_HINT,
} from "./buildCheck";
import { UI_BUILD } from "./uiBuild";
import {
  DEFAULT_CONFIG,
  chartRefreshMs,
  fmtKrw,
  isRunning,
  mergeWsPayload,
  MIN_BUY_KRW,
  roundPct2,
} from "./utils";

export default function App() {
  const [data, setData] = useState<StatusPayload | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [configDraft, setConfigDraft] = useState<AppConfig>(DEFAULT_CONFIG);
  const [chartInterval, setChartInterval] = useState("1h");
  const [activeSymbol, setActiveSymbol] = useState("BTCUSDT");
  const [candles, setCandles] = useState<Candle[]>([]);
  const [chartLoading, setChartLoading] = useState(false);
  const [chartError, setChartError] = useState<string | null>(null);
  const [chartLevels, setChartLevels] = useState<ChartTradeLevels | null>(null);
  const [chartMarkers, setChartMarkers] = useState<ChartMarkerDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [botBusy, setBotBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [autoLong, setAutoLong] = useState(true);
  const [autoScalp, setAutoScalp] = useState(false);
  const [mainView, setMainView] = useState<MainView>("chart");
  const [tradeBusy, setTradeBusy] = useState(false);

  const botLockVersionRef = useRef(0);
  const activeSymbolRef = useRef(activeSymbol);

  const botRecs = data?.bot.recommendations ?? [];
  const appConfig = data?.config ?? DEFAULT_CONFIG;
  const {
    list: editableRecs,
    aiAmounts,
    setAmount: setRecAmount,
    resetToAi: resetRecAi,
    getApplyItems,
  } = useRecommendationAmounts(
    botRecs,
    appConfig,
    data?.portfolio.cash_krw ?? 0
  );
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

  // 차트 탭에서만 로드 (자금/알림 탭에서 BTC 등 불필요 요청 방지)
  useEffect(() => {
    if (mainView !== "chart") return;
    let cancelled = false;
    let initial = true;
    const sym = activeSymbol;
    const iv = chartInterval;

    const load = async () => {
      if (initial) {
        setChartLoading(true);
        setChartError(null);
      }
      try {
        const res = await fetchChart(sym, iv);
        if (!cancelled && activeSymbolRef.current === sym) {
          setCandles(res.candles || []);
          setChartLevels(res.levels ?? null);
          setChartMarkers(res.markers ?? []);
          if (res.stale) {
            setChartError(
              res.chart_error || "업비트 요청 제한 — 잠시 후 자동 갱신됩니다"
            );
          } else {
            setChartError(null);
          }
        }
      } catch (e) {
        if (!cancelled && activeSymbolRef.current === sym) {
          setCandles([]);
          setChartError(e instanceof Error ? e.message : "차트 로드 실패");
        }
      } finally {
        if (!cancelled && initial) {
          setChartLoading(false);
          initial = false;
        }
      }
    };

    load();
    const timerId = window.setInterval(load, chartRefreshMs(iv));
    return () => {
      cancelled = true;
      window.clearInterval(timerId);
    };
  }, [activeSymbol, chartInterval, mainView]);

  const handleSelectCoin = useCallback(
    async (sym: string) => {
      setActiveSymbol(sym);
      setCandles([]);
      setChartLevels(null);
      setChartMarkers([]);
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

  const startAutoInvest = async () => {
    if (botBusy || !data || running || stopping) return;
    const isLiveMode = data.config.trade_mode === "live";
    if (isLiveMode && !data.config.allow_live_auto_invest) {
      showToast(
        "설정에서 「실거래 자동투자 허용」을 켜고 저장한 뒤 다시 시도하세요"
      );
      return;
    }
    if (isLiveMode && !data.account_link?.linked) {
      showToast("실거래: API 키 저장·연결 테스트 후 자동 투자를 시작하세요");
      return;
    }
    if (!autoLong && !autoScalp) {
      showToast("롱 또는 단타를 하나 이상 체크하세요");
      return;
    }
    setBotBusy(true);
    botLockVersionRef.current = (data.status_version ?? 0) + 1000;
    try {
      setData({
        ...data,
        bot: {
          ...data.bot,
          status: "running",
          message: "자동투자 시작 중…",
          auto_invest_active: true,
          auto_invest_long: autoLong,
          auto_invest_scalp: autoScalp,
        },
      });
      const s = await startBot({
        auto_invest: true,
        auto_long: autoLong,
        auto_scalp: autoScalp,
      });
      botLockVersionRef.current = s.status_version ?? botLockVersionRef.current;
      setData(s);
      if (s.ok === false) {
        showToast(s.message || "자동투자를 시작할 수 없습니다");
      } else {
        const mix =
          autoLong && autoScalp
            ? "롱·단타 혼합"
            : autoLong
              ? "롱"
              : "단타";
        const modeLabel = isLiveMode ? "실거래" : "모의";
        showToast(
          s.message ||
            `${modeLabel} 완전자동(${mix}) · BT·스캔·매수·익절/손절`
        );
      }
    } catch (e) {
      showToast(e instanceof Error ? e.message : "요청 실패");
      const s = await fetchStatus();
      applyPayload(s);
    } finally {
      setBotBusy(false);
    }
  };

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
        showToast("분석을 중지했습니다");
      } else {
        setData({
          ...data,
          bot: { ...data.bot, status: "running", message: "분석 중..." },
        });
        const s = await startBot({});
        botLockVersionRef.current = s.status_version ?? botLockVersionRef.current;
        setData(s);
        if (s.ok === false) {
          showToast(s.message || "시작할 수 없습니다");
        } else {
          showToast("시장 분석을 시작했습니다 · 제안 확인 후 승인 매수");
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

  const handleManualBuy = async (symbol: string, amountKrw: number) => {
    setTradeBusy(true);
    try {
      const s = await manualBuy(symbol, amountKrw);
      applyPayload(s);
      showToast(s.message || "매수 완료");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "매수 실패");
    } finally {
      setTradeBusy(false);
    }
  };

  const handleManualSell = async (symbol: string, percent: number) => {
    setTradeBusy(true);
    try {
      const s = await manualSell(symbol, percent);
      applyPayload(s);
      showToast(s.message || "매도 완료");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "매도 실패");
    } finally {
      setTradeBusy(false);
    }
  };

  const handleSellAll = async () => {
    const n = data?.portfolio.positions.length ?? 0;
    if (n === 0) {
      showToast("보유 코인이 없습니다");
      return;
    }
    if (
      !window.confirm(
        `보유 중인 ${n}개 코인을 100% 전체 매도하시겠습니까?\n(실거래·모의 모두 즉시 체결됩니다)`
      )
    ) {
      return;
    }
    setTradeBusy(true);
    try {
      const s = await sellAll(100);
      applyPayload(s);
      showToast(s.message || "전체 매도 완료");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "전체 매도 실패");
    } finally {
      setTradeBusy(false);
    }
  };

  const goChart = (sym: string) => {
    setMainView("chart");
    handleSelectCoin(sym);
  };

  const handleSaveSettings = async () => {
    setSaving(true);
    try {
      const toSave: AppConfig = {
        ...configDraft,
        stop_loss_pct: roundPct2(configDraft.stop_loss_pct),
        take_profit_pct: roundPct2(configDraft.take_profit_pct),
      };
      setConfigDraft(toSave);
      const s = await saveConfig(toSave);
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
  const isLiveMode = data.config.trade_mode === "live";
  const allowLiveAuto = !!data.config.allow_live_auto_invest;
  const buildId = data.aidi_build || "";
  const caps = data.aidi_capabilities;
  const serverNewEnough = isServerBuildNewEnough(buildId, caps);
  const needPcUpdate = !serverNewEnough;
  const uiStale =
    serverNewEnough &&
    !!buildId &&
    buildId !== UI_BUILD &&
    !isBuildGenerationCompatible(buildId, UI_BUILD, caps);
  const canTrade = !stopping;
  const activeRec =
    editableRecs.find((r) => r.symbol === activeSymbol) ?? null;
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

  const handleQuickBuy = (symbol: string) => {
    const cash = data?.portfolio.cash_krw ?? 0;
    const amount = Math.max(
      MIN_BUY_KRW,
      Math.min(Math.floor(cash * 0.25), Math.floor(cash * 0.95))
    );
    handleManualBuy(symbol, amount);
  };

  const pairLabel =
    data.portfolio.positions.find((p) => p.symbol === activeSymbol)?.pair_label ||
    data.bot.candidates.find((c) => c.symbol === activeSymbol)?.pair_label ||
    `${activeSymbol.replace("USDT", "")}/USDT`;

  const applyRecs = async (symbolsOrItems: string[] | ApplyItem[]) => {
    setTradeBusy(true);
    try {
      const items: ApplyItem[] =
        symbolsOrItems.length > 0 && typeof symbolsOrItems[0] === "object"
          ? (symbolsOrItems as ApplyItem[])
          : getApplyItems(symbolsOrItems as string[]);
      const symbols = items.map((i) => i.symbol);
      const s = await applyRecommendations(symbols, items);
      applyPayload(s);
      showToast(s.message || "매수 완료");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "매수 실패");
    } finally {
      setTradeBusy(false);
    }
  };

  return (
    <div className="app">
      <div className="app-top">
        <div className={`mode-banner ${isPaper ? "paper" : "live"}`}>
          {needPcUpdate ? (
            <strong style={{ display: "block", marginBottom: 4 }}>
              ⚠ 백엔드 구버전 — GitHub ZIP 덮어쓰기 → stop-aidi.bat → run.bat
              <br />
              <span style={{ fontWeight: 400, fontSize: "0.85em" }}>
                서버 빌드: {buildId || "없음"} · {REQUIRED_BUILD_HINT}
              </span>
            </strong>
          ) : uiStale ? (
            <span
              style={{
                display: "block",
                fontSize: "0.85em",
                marginBottom: 4,
                opacity: 0.92,
              }}
            >
              화면만 구버전 — run.bat 한 번 실행 후 Ctrl+F5 (서버{" "}
              {buildId} · UI {UI_BUILD})
            </span>
          ) : null}
          {isPaper
            ? `모의투자 · ${fmtKrw(data.portfolio.total_value_krw)}원`
            : data.account_link?.linked
              ? `실거래 · 총자산 ${fmtKrw(data.account_link.total_assets_krw ?? data.portfolio.total_value_krw)}원`
              : `실거래 — ${data.account_link?.message || "API 연동 필요"}`}
          {data.bot.auto_risk?.kill_switch &&
          (!data.bot.auto_risk.risk_mode ||
            data.bot.auto_risk.risk_mode === data.config.trade_mode) ? (
            <div className="kill-switch-banner">
              <strong>
                일손실 킬 스위치 (
                {data.config.trade_mode === "live" ? "실거래" : "모의"})
              </strong>{" "}
              — {data.bot.auto_risk.kill_reason || "자동 매수 중지"}
              <button
                type="button"
                className="btn-ghost btn-xs"
                onClick={async () => {
                  try {
                    const s = await resetRiskKill();
                    applyPayload(s);
                    showToast(s.message || "킬 스위치 해제");
                  } catch (e) {
                    showToast(e instanceof Error ? e.message : "해제 실패");
                  }
                }}
              >
                해제
              </button>
            </div>
          ) : data.bot.auto_invest_active && data.bot.auto_risk?.message ? (
            <div className="risk-status-line">{data.bot.auto_risk.message}</div>
          ) : null}
        </div>

        <header className="topbar topbar-compact topbar-with-funds">
          <div className="brand">
            <span className="logo">AIDI</span>
          </div>
          <FundsSummaryStrip
            portfolio={data.portfolio}
            config={data.config}
            variant="topbar"
          />
          <div className="top-actions">
            {!running && !stopping ? (
              <div
                className="auto-invest-opts"
                title={
                  isPaper
                    ? "모의투자 완전 자동화"
                    : "실거래 완전 자동화 (업비트 API)"
                }
              >
                <label className="auto-check">
                  <input
                    type="checkbox"
                    checked={autoLong}
                    onChange={(e) => setAutoLong(e.target.checked)}
                  />
                  롱
                </label>
                <label className="auto-check">
                  <input
                    type="checkbox"
                    checked={autoScalp}
                    onChange={(e) => setAutoScalp(e.target.checked)}
                  />
                  단타
                </label>
                <button
                  type="button"
                  className="btn-secondary btn-auto-start"
                  onClick={startAutoInvest}
                  disabled={botBusy}
                >
                  {isLiveMode ? "실거래 자동 투자" : "자동 투자 시작"}
                </button>
                {isLiveMode && !allowLiveAuto && (
                  <span className="auto-live-hint dim">
                    설정에서 허용 필요
                  </span>
                )}
              </div>
            ) : data.bot.auto_invest_active ? (
              <>
                <span className="auto-invest-badge">
                  자동
                  {data.bot.auto_invest_long && data.bot.auto_invest_scalp
                    ? " 롱·단타"
                    : data.bot.auto_invest_long
                      ? " 롱"
                      : " 단타"}
                  {data.bot.auto_buy_paused ? " · 매수중지" : ""}
                </span>
                <button
                  type="button"
                  className="btn-ghost btn-xs"
                  disabled={botBusy}
                  onClick={async () => {
                    setBotBusy(true);
                    try {
                      const s = await setAutoBuyPaused(!data.bot.auto_buy_paused);
                      applyPayload(s);
                      showToast(s.message || "상태 변경");
                    } catch (e) {
                      showToast(e instanceof Error ? e.message : "실패");
                    } finally {
                      setBotBusy(false);
                    }
                  }}
                >
                  {data.bot.auto_buy_paused ? "매수 재개" : "매수만 중지"}
                </button>
              </>
            ) : null}
            <button
              type="button"
              className="btn-ghost btn-settings"
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
              {stopping ? "중지 중..." : running ? "중지" : "분석 시작"}
            </button>
          </div>
        </header>

        <nav className="main-nav">
          <button
            type="button"
            className={`nav-btn ${mainView === "alerts" ? "active" : ""}`}
            onClick={() => setMainView("alerts")}
          >
            알림
            {(editableRecs.length > 0 ||
              (data?.bot.long_signals?.length ?? 0) > 0 ||
              (data?.bot.short_signals?.length ?? 0) > 0) && (
              <span className="nav-badge">
                {editableRecs.length +
                  (data?.bot.long_signals?.length ?? 0) +
                  (data?.bot.short_signals?.length ?? 0)}
              </span>
            )}
          </button>
          <button
            type="button"
            className={`nav-btn ${mainView === "stats" ? "active" : ""}`}
            onClick={() => setMainView("stats")}
          >
            통계
          </button>
          <button
            type="button"
            className={`nav-btn ${mainView === "chart" ? "active" : ""}`}
            onClick={() => setMainView("chart")}
          >
            차트 · AI
          </button>
          <button
            type="button"
            className={`nav-btn ${mainView === "funds" ? "active" : ""}`}
            onClick={() => setMainView("funds")}
          >
            보유 · 매매
          </button>
        </nav>
      </div>

      {running && (
        <div className="activity-strip-wrap">
          <ActivityPanel bot={data.bot} />
        </div>
      )}
      {data.bot.scan_health && data.bot.scan_health !== "ok" && (
        <div className="scan-health-banner warn">
          {data.bot.scan_health_detail ||
            "시장 데이터 지연 — 스캔이 잠시 중지될 수 있습니다"}
        </div>
      )}

      {mainView === "stats" && (
        <StatsTab
          portfolio={data.portfolio}
          trades={data.all_trades ?? data.bot.recent_trades}
          bot={data.bot}
          configMode={data.config.trade_mode}
        />
      )}

      {mainView === "alerts" && (
        <AlertsHub
          recommendations={editableRecs}
          longSignals={data.bot.long_signals ?? []}
          shortSignals={data.bot.short_signals ?? []}
          directionMessage={data.bot.direction_scan_message}
          backtestMessage={data.bot.backtest?.message}
          backtest={data.bot.backtest}
          autoInvestMessage={data.bot.auto_invest_message}
          bot={data.bot}
          botStatus={data.bot.status}
          cashKrw={data.portfolio.cash_krw}
          feePct={appConfig.trading_fee_pct}
          busy={tradeBusy}
          onApplyRecs={applyRecs}
          onScanDirection={async (side) => {
            const s = await scanDirectionSignals(side);
            applyPayload(s);
            setToast(s.message ?? (side === "long" ? "롱 분석 완료" : "숏 분석 완료"));
          }}
          onOpenChart={() => setMainView("chart")}
          onSelectSymbol={goChart}
        />
      )}

      {mainView === "chart" && (
        <div className="chart-screen">
          <CoinSearchTabs
            tabs={tabs}
            selected={activeSymbol}
            portfolio={data.portfolio}
            candidates={data.bot.candidates}
            tabQuotes={data.tab_quotes}
            onSelect={handleSelectCoin}
          />
          <main className="layout chart-layout">
            <aside className="side-panel">
              <RecommendationsPanel
                variant="sidebar"
                list={editableRecs}
                aiAmounts={aiAmounts}
                botStatus={data.bot.status}
                cashKrw={data.portfolio.cash_krw}
                feePct={appConfig.trading_fee_pct ?? 0.05}
                busy={tradeBusy}
                onAmountChange={setRecAmount}
                onResetAi={resetRecAi}
                onApply={applyRecs}
              />
              <div className="side-panel-scroll">
                <PortfolioPanel
                  portfolio={data.portfolio}
                  candidates={data.bot.candidates}
                  trades={data.all_trades ?? data.bot.recent_trades}
                  selected={activeSymbol}
                  onSelect={handleSelectCoin}
                  canTrade={canTrade}
                  busy={tradeBusy}
                  onQuickBuy={handleQuickBuy}
                  onSellAll={handleSellAll}
                />
              </div>
            </aside>
            <div className="chart-column">
              <CoinDetailBar
                view={view}
                botStatus={data.bot.status}
                botMessage={data.bot.message}
                canTrade={canTrade}
                busy={tradeBusy}
                cashKrw={data.portfolio.cash_krw}
                config={appConfig}
                recommendation={activeRec}
                tabQuote={data.tab_quotes?.[activeSymbol]}
                onBuy={handleManualBuy}
                onSell={handleManualSell}
              />
              <ChartPanel
                symbol={activeSymbol}
                pairLabel={pairLabel}
                chartInterval={chartInterval}
                candles={candles}
                chartLoading={chartLoading}
                chartError={chartError}
                tradeLevels={chartLevels}
                tradeMarkers={chartMarkers}
                onIntervalChange={setChartInterval}
              />
            </div>
          </main>
        </div>
      )}

      {mainView === "funds" && (
        <div className="funds-screen scroll-y">
          <PortfolioAllocationPanel portfolio={data.portfolio} />
          <RecommendationsPanel
            variant="full"
            list={editableRecs}
            aiAmounts={aiAmounts}
            botStatus={data.bot.status}
            cashKrw={data.portfolio.cash_krw}
            feePct={appConfig.trading_fee_pct ?? 0.05}
            busy={tradeBusy}
            onAmountChange={setRecAmount}
            onResetAi={resetRecAi}
            onApply={applyRecs}
          />
          <FundsTab
            portfolio={data.portfolio}
            trades={data.all_trades ?? data.bot.recent_trades}
            botStatus={data.bot.status}
            manualMode={data.bot.manual_mode}
            tradeMode={data.config.trade_mode}
            tradesSyncError={data.trades_sync_error}
            tradesDisplayCount={data.trades_display_count}
            tradesOrdersFetched={data.trades_orders_fetched}
            upbitSnapshot={data.upbit_snapshot}
            onManualBuy={handleManualBuy}
            onManualSell={handleManualSell}
            onSellAll={handleSellAll}
            onSelectChart={goChart}
            onExclude={async (sym, ex) => {
              setTradeBusy(true);
              try {
                const s = await setPositionExclude(sym, ex);
                applyPayload(s);
                showToast(s.message || (ex ? "자동투자 제외" : "제외 해제"));
              } catch (e) {
                showToast(e instanceof Error ? e.message : "실패");
              } finally {
                setTradeBusy(false);
              }
            }}
            onExitPlan={async (sym, plan) => {
              setTradeBusy(true);
              try {
                const s = await setPositionExitPlan(sym, plan);
                applyPayload(s);
                showToast(s.message || "손익절 설정 저장");
              } catch (e) {
                showToast(e instanceof Error ? e.message : "손익절 저장 실패");
              } finally {
                setTradeBusy(false);
              }
            }}
            onMigrateExits={async () => {
              setTradeBusy(true);
              try {
                const s = await migratePositionExits(true);
                applyPayload(s);
                showToast(s.message || "손익절 재적용");
              } catch (e) {
                showToast(e instanceof Error ? e.message : "실패");
              } finally {
                setTradeBusy(false);
              }
            }}
            stopLossPct={data.config.stop_loss_pct}
            takeProfitPct={data.config.take_profit_pct}
            busy={tradeBusy}
          />
        </div>
      )}

      {toast && <div className="toast">{toast}</div>}

      {settingsOpen && (
        <SettingsModal
          config={data.config}
          draft={configDraft}
          onChange={setConfigDraft}
          onSave={handleSaveSettings}
          onClose={() => setSettingsOpen(false)}
          saving={saving}
          onAfterReset={(s) => {
            applyPayload(s);
            setConfigDraft(s.config);
            showToast(s.message || "초기화 완료");
          }}
        />
      )}
    </div>
  );
}
