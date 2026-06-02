import { useState } from "react";
import { resetBacktestData, resetPaperData, testCredentials } from "../api";
import type { StatusPayload } from "../types";
import type { AppConfig } from "../types";
import { fmtKrw, getMinBuyKrw, roundPct2 } from "../utils";
import MinBuyKrwPanel from "./MinBuyKrwPanel";

type Props = {
  config: AppConfig;
  draft: AppConfig;
  onChange: (c: AppConfig) => void;
  onSave: () => void;
  onClose: () => void;
  saving: boolean;
  onAfterReset?: (status: StatusPayload) => void;
  onSaveMinBuyKrw?: (minBuyKrw: number) => Promise<void>;
};

export default function SettingsModal({
  config,
  draft,
  onChange,
  onSave,
  onClose,
  saving,
  onAfterReset,
  onSaveMinBuyKrw,
}: Props) {
  const [testing, setTesting] = useState(false);
  const [resetBusy, setResetBusy] = useState<"paper" | "backtest" | null>(null);
  const [testMsg, setTestMsg] = useState<string | null>(null);
  const [testOk, setTestOk] = useState<boolean | null>(null);

  const set = <K extends keyof AppConfig>(key: K, value: AppConfig[K]) => {
    onChange({ ...draft, [key]: value });
    setTestMsg(null);
    setTestOk(null);
  };

  const exchange = draft.exchange || "upbit";
  const maskedAk = config.api_access_key_masked || config.binance_api_key;
  const maskedSk = config.api_secret_key_masked;
  const hasSaved = config.has_saved_keys;

  const handleTest = async () => {
    setTesting(true);
    setTestMsg(null);
    try {
      const res = await testCredentials(draft);
      if (res.ok) {
        setTestOk(true);
        if (res.exchange === "upbit" || res.accounts != null) {
          const ipNote = res.outbound_ip || res.outbound_ipv4_stack;
          const ipStr = ipNote ? ` · IP ${ipNote}` : "";
          const acct = res.accounts ?? res.coin_count ?? 0;
          setTestMsg(res.message || `연결 성공 · 계정 ${acct}개${ipStr}`);
        } else {
          setTestMsg(res.message || "연결 성공");
        }
      } else {
        setTestOk(false);
        const parts = [res.message || "연결 실패"];
        if (res.upbit_error_name) parts.push(`[${res.upbit_error_name}]`);
        if (res.outbound_ip || res.outbound_ipv4_stack) {
          parts.push(`IP ${res.outbound_ip || res.outbound_ipv4_stack}`);
        }
        if (res.access_key_hint) parts.push(`키 ${res.access_key_hint}`);
        if (res.key_source) parts.push(`(${res.key_source})`);
        if (res.hint) parts.push(res.hint);
        setTestMsg(parts.join(" · "));
      }
    } catch (e) {
      setTestOk(false);
      setTestMsg(e instanceof Error ? e.message : "연결 실패");
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div
        className="modal modal-wide settings-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
      >
        <h2>설정</h2>

        <MinBuyKrwPanel
          value={getMinBuyKrw(draft)}
          saving={saving}
          onSave={async (n) => {
            set("min_buy_krw", n);
            if (onSaveMinBuyKrw) {
              await onSaveMinBuyKrw(n);
              return;
            }
            const r = await fetch("/api/config/min-buy-krw", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ min_buy_krw: n }),
            });
            if (!r.ok) {
              const j = await r.json().catch(() => ({}));
              throw new Error(
                (j as { message?: string }).message || "저장 실패"
              );
            }
          }}
        />

        <section className="settings-section">
          <h3>투자 모드</h3>
          <div className="mode-toggle">
            <button
              type="button"
              className={`mode-btn paper ${draft.trade_mode === "paper" ? "active" : ""}`}
              onClick={() => set("trade_mode", "paper")}
            >
              <strong>모의투자</strong>
              <span>실제 주문 없음 · 연습/테스트</span>
            </button>
            <button
              type="button"
              className={`mode-btn live ${draft.trade_mode === "live" ? "active" : ""}`}
              onClick={() => set("trade_mode", "live")}
            >
              <strong>실거래</strong>
              <span>거래소 API · 실제 자금</span>
            </button>
          </div>
          {draft.trade_mode === "live" && (
            <p className="warn">
              실거래는 거래소 잔고·보유 코인을 API로 불러옵니다. 모의투자 데이터와 섞이지
              않습니다. 연결 테스트 후 소액으로 확인하세요.
            </p>
          )}
          {draft.trade_mode === "paper" && (
            <p className="warn subtle">
              모의투자 잔고는 앱 내부 시뮬이며, 실거래 계정과 무관합니다.
            </p>
          )}
          <p className="warn subtle">
            AI 승인 매수·익절/손절·자동투자 제외·분석 중지 후 감시는 모의/실거래
            동일합니다. 실거래만 거래소 주문·잔고 동기화가 추가됩니다.
          </p>
        </section>

        <section className="settings-section settings-exit-strength">
          <h3>자동투자 청산 강도</h3>
          <p className="warn subtle">
            AI 자동 매수 포지션의 익절·손절 목표와 추적 방식입니다. 약은 기존 단타(~1%),
            중·강은 목표를 넓히고 상승 시 손절·익절선을 따라 올립니다.
            <strong> 급등주·뉴스급등은 약·중·강과 무관</strong>하게 24h 기세 기반
            손익절이 자동 적용됩니다.
          </p>
          <div className="mode-toggle exit-strength-toggle">
            <button
              type="button"
              className={`mode-btn ${(draft.auto_exit_strength || "weak") === "weak" ? "active" : ""}`}
              onClick={() => set("auto_exit_strength", "weak")}
            >
              <strong>약</strong>
              <span>익절 ~1.2% · 손절 ~2.5% · 고정 단타</span>
            </button>
            <button
              type="button"
              className={`mode-btn ${draft.auto_exit_strength === "medium" ? "active" : ""}`}
              onClick={() => set("auto_exit_strength", "medium")}
            >
              <strong>중</strong>
              <span>익절 ~3% · 손절 ~4.5% · 추적 조율</span>
            </button>
            <button
              type="button"
              className={`mode-btn ${draft.auto_exit_strength === "strong" ? "active" : ""}`}
              onClick={() => set("auto_exit_strength", "strong")}
            >
              <strong>강</strong>
              <span>익절 ~6% · 손절 ~7% · 넓은 추적</span>
            </button>
          </div>
        </section>

        <section className="settings-section">
          <h3>급등주 손익절</h3>
          <p className="panel-hint subtle">
            24h 상승률·뉴스 점수로 손익절 구간을 자동 산출합니다. 약·중·강 청산 강도와
            별도로 동작합니다.
          </p>
          <label className="field checkbox-field">
            <input
              type="checkbox"
              checked={draft.moonshot_momentum_exit_enabled !== false}
              onChange={(e) =>
                set("moonshot_momentum_exit_enabled", e.target.checked)
              }
            />
            <span>기세 기반 손익절 자동 (권장)</span>
          </label>
          <div className="field-grid">
            <label className="field">
              <span>손절 하한 %</span>
              <input
                type="number"
                step={0.5}
                min={3}
                max={12}
                value={draft.moonshot_min_stop_loss_pct ?? 4}
                onChange={(e) =>
                  set("moonshot_min_stop_loss_pct", Number(e.target.value))
                }
              />
            </label>
            <label className="field">
              <span>손절 상한 %</span>
              <input
                type="number"
                step={0.5}
                min={3}
                max={15}
                value={draft.moonshot_max_stop_loss_pct ?? 10}
                onChange={(e) =>
                  set("moonshot_max_stop_loss_pct", Number(e.target.value))
                }
              />
            </label>
            <label className="field">
              <span>익절 하한 %</span>
              <input
                type="number"
                step={1}
                min={3}
                max={50}
                value={draft.moonshot_min_take_profit_pct ?? 10}
                onChange={(e) =>
                  set("moonshot_min_take_profit_pct", Number(e.target.value))
                }
              />
            </label>
            <label className="field">
              <span>익절 상한 %</span>
              <input
                type="number"
                step={1}
                min={5}
                max={50}
                value={draft.moonshot_max_take_profit_pct ?? 35}
                onChange={(e) =>
                  set("moonshot_max_take_profit_pct", Number(e.target.value))
                }
              />
            </label>
          </div>
        </section>

        <section className="settings-section">
          <h3>목표 · 자금</h3>
          <div className="field-grid">
            <label className="field">
              <span>목표 수익 (원)</span>
              <input
                type="number"
                value={draft.target_profit_krw}
                onChange={(e) => set("target_profit_krw", Number(e.target.value))}
              />
            </label>
            {draft.trade_mode === "paper" ? (
              <label className="field">
                <span>모의투자 시작 자금 (원)</span>
                <input
                  type="number"
                  value={draft.initial_balance_krw}
                  onChange={(e) => set("initial_balance_krw", Number(e.target.value))}
                />
                <small>포지션·체결 없을 때만 반영 · 현재 {fmtKrw(config.initial_balance_krw)}원</small>
              </label>
            ) : (
              <div className="field">
                <span>실거래 자금</span>
                <p className="warn subtle" style={{ margin: "0.35rem 0 0" }}>
                  업비트/Binance API로 <strong>실제 잔고·보유 코인</strong>을 불러옵니다.
                  시작 자금은 수동 입력하지 않습니다. 연결 테스트 후 자금 탭에서 확인하세요.
                </p>
              </div>
            )}
          </div>
        </section>

        <section className="settings-section">
          <h3>뉴스 급등 보조</h3>
          <p className="panel-hint subtle">
            CoinDesk·CoinTelegraph RSS, CoinGecko 트렌딩, (선택) CryptoPanic으로
            기사 키워드를 점수화합니다. 아래 AI 판단을 켜면 헤드라인 맥락도 반영합니다.
          </p>
          <label className="field checkbox-field">
            <input
              type="checkbox"
              checked={draft.news_enabled !== false}
              onChange={(e) => set("news_enabled", e.target.checked)}
            />
            <span>뉴스 급등 신호 사용</span>
          </label>
          <div className="field-grid">
            <label className="field">
              <span>뉴스급등 최소 점수</span>
              <input
                type="number"
                step={1}
                min={10}
                max={80}
                value={draft.news_boost_min_score ?? 25}
                onChange={(e) =>
                  set("news_boost_min_score", Number(e.target.value))
                }
              />
            </label>
            <label className="field">
              <span>CryptoPanic API 키 (선택)</span>
              <input
                type="password"
                autoComplete="off"
                placeholder="없으면 RSS·CoinGecko만 사용"
                value={draft.cryptopanic_api_key ?? ""}
                onChange={(e) => set("cryptopanic_api_key", e.target.value)}
              />
            </label>
          </div>
          <label className="field checkbox-field">
            <input
              type="checkbox"
              checked={draft.surge_auto_expire_enabled !== false}
              onChange={(e) => set("surge_auto_expire_enabled", e.target.checked)}
            />
            <span>급등·하락 자동 만료 (기사 분류)</span>
          </label>
          <p className="panel-hint subtle">
            뉴스·AI로 분류된 급등·하락 태그는 아래 시간이 지나면 해제됩니다. 같은
            종목에 관련 기사가 다시 잡히면 만료 시각이 연장됩니다. 24h 가격 급등
            (moonshot)은 별도 기준으로 매 스캔 판단합니다. 보유 중 포지션의 청산
            프로필은 만료와 무관하게 유지됩니다.
          </p>
          <div className="field-grid">
            <label className="field">
              <span>급등주 유지 (시간)</span>
              <input
                type="number"
                step={1}
                min={1}
                max={168}
                disabled={draft.surge_auto_expire_enabled === false}
                value={draft.surge_tag_ttl_hours ?? 48}
                onChange={(e) =>
                  set("surge_tag_ttl_hours", Number(e.target.value))
                }
              />
            </label>
            <label className="field">
              <span>하락주 유지 (시간)</span>
              <input
                type="number"
                step={1}
                min={1}
                max={168}
                disabled={draft.surge_auto_expire_enabled === false}
                value={draft.downtrend_tag_ttl_hours ?? 24}
                onChange={(e) =>
                  set("downtrend_tag_ttl_hours", Number(e.target.value))
                }
              />
            </label>
          </div>
        </section>

        <section className="settings-section">
          <h3>뉴스 AI 판단 (Gemini)</h3>
          <p className="panel-hint subtle">
            Google Gemini가 헤드라인 맥락을 분석합니다. 제목에 &apos;급등&apos;이 있어도
            AI가 하락·부정으로 보면 뉴스급등·급등(moonshot) 보조를 차단합니다.
            스캔당 최대 {draft.news_llm_max_articles_per_scan ?? 8}건 API 호출.
          </p>
          <label className="field checkbox-field">
            <input
              type="checkbox"
              checked={draft.news_llm_enabled === true}
              onChange={(e) => set("news_llm_enabled", e.target.checked)}
            />
            <span>뉴스 AI 방향 판단 사용 (Gemini)</span>
          </label>
          <label className="field checkbox-field">
            <input
              type="checkbox"
              checked={draft.backtest_ai_enabled === true}
              onChange={(e) => set("backtest_ai_enabled", e.target.checked)}
            />
            <span>백테스트 AI 학습 (Gemini, 위 API 키 공유)</span>
          </label>
          <p className="panel-hint subtle">
            백테스트 배치마다 상·하위 종목 요약을 Gemini에 보내 손절/익절·차단·롱/단타
            방향을 제안합니다. 배치당 최대 {draft.backtest_ai_max_symbols_per_batch ?? 5}
            종목 · 기본 꺼짐.
          </p>
          <div className="field-grid">
            <label className="field">
              <span>Gemini API 키</span>
              <input
                type="password"
                autoComplete="off"
                placeholder="AIza… (Google AI Studio에서 발급)"
                value={draft.gemini_api_key ?? draft.news_llm_api_key ?? ""}
                onChange={(e) => {
                  const v = e.target.value;
                  onChange({
                    ...draft,
                    gemini_api_key: v,
                    news_llm_api_key: v,
                    news_llm_provider: "gemini",
                  });
                  setTestMsg(null);
                }}
              />
              <small>
                키 없으면 키워드 점수만 사용 ·{" "}
                <a
                  href="https://aistudio.google.com/apikey"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  API 키 발급
                </a>
              </small>
            </label>
            <label className="field">
              <span>스캔당 최대 기사 수</span>
              <input
                type="number"
                step={1}
                min={1}
                max={20}
                value={draft.news_llm_max_articles_per_scan ?? 8}
                onChange={(e) =>
                  set("news_llm_max_articles_per_scan", Number(e.target.value))
                }
              />
            </label>
          </div>
          <details className="settings-advanced">
            <summary>고급 (OpenAI 대체)</summary>
            <div className="field-grid" style={{ marginTop: 8 }}>
              <label className="field">
                <span>AI 제공자</span>
                <select
                  value={draft.news_llm_provider ?? "gemini"}
                  onChange={(e) => set("news_llm_provider", e.target.value)}
                >
                  <option value="gemini">Google Gemini (기본)</option>
                  <option value="openai">OpenAI (대체)</option>
                  <option value="auto">자동 (Gemini 우선)</option>
                </select>
              </label>
              <label className="field">
                <span>OpenAI API 키 (대체)</span>
                <input
                  type="password"
                  autoComplete="off"
                  placeholder="sk-… (선택)"
                  value={draft.openai_api_key ?? ""}
                  onChange={(e) => set("openai_api_key", e.target.value)}
                />
              </label>
            </div>
          </details>
        </section>

        <section className="settings-section">
          <h3>급락 방어</h3>
          <p className="warn subtle">
            익절 전이라도 고점·순간·1분봉 급락이면 전량 매도합니다. 급락 후 해당 종목
            신규 매수는 일시 차단됩니다.
          </p>
          <label className="field checkbox-field">
            <input
              type="checkbox"
              checked={draft.flash_guard_enabled !== false}
              onChange={(e) => set("flash_guard_enabled", e.target.checked)}
            />
            <span>급락 감지·즉시 손절 사용</span>
          </label>
          <div className="field-grid">
            <label className="field">
              <span>고점 대비 하락 (%)</span>
              <input
                type="number"
                step={0.1}
                min={0.5}
                max={15}
                value={draft.flash_drop_from_peak_pct ?? 2.8}
                onChange={(e) =>
                  set("flash_drop_from_peak_pct", Number(e.target.value))
                }
              />
            </label>
            <label className="field">
              <span>순간 하락 (%)</span>
              <input
                type="number"
                step={0.1}
                min={0.3}
                max={8}
                value={draft.flash_tick_drop_pct ?? 1.2}
                onChange={(e) => set("flash_tick_drop_pct", Number(e.target.value))}
              />
            </label>
            <label className="field">
              <span>1분봉 급락 (%)</span>
              <input
                type="number"
                step={0.1}
                min={1}
                max={20}
                value={draft.flash_candle_1m_drop_pct ?? 3.5}
                onChange={(e) =>
                  set("flash_candle_1m_drop_pct", Number(e.target.value))
                }
              />
            </label>
            <label className="field">
              <span>급락 후 매수 차단 (분)</span>
              <input
                type="number"
                min={5}
                max={240}
                value={draft.flash_block_minutes ?? 45}
                onChange={(e) => set("flash_block_minutes", Number(e.target.value))}
              />
            </label>
          </div>
        </section>

        <section className="settings-section">
          <h3>AI 자동 설정</h3>
          <label className="field checkbox-field">
            <input
              type="checkbox"
              checked={draft.ai_auto_settings !== false}
              onChange={(e) => set("ai_auto_settings", e.target.checked)}
            />
            <span>
              백테스트·학습으로 손익절·스캔 점수·자동 배분 조정 (권장)
            </span>
          </label>
          <p className="warn subtle">
            켜면 아래 숫자는 BT가 바꿉니다. 끄면 직접 입력값을 사용합니다. 수수료
            0.05%·일손실 킬만 고정 권장.
          </p>
        </section>

        <section className="settings-section">
          <h3>매매 전략</h3>
          {draft.ai_auto_settings !== false && (
            <p className="warn subtle">
              AI 자동 ON — 손절/익절·스캔 점수는 실행 중 BT가 조정합니다.
            </p>
          )}
          <div className="field-grid">
            <label className="field">
              <span>손절 (%) · 소수 둘째 자리</span>
              <input
                type="number"
                min={0.01}
                max={25}
                step={0.01}
                value={draft.stop_loss_pct}
                onChange={(e) =>
                  set("stop_loss_pct", roundPct2(Number(e.target.value)))
                }
                onBlur={(e) =>
                  set("stop_loss_pct", roundPct2(Number(e.target.value)))
                }
              />
            </label>
            <label className="field">
              <span>익절 (%) · 소수 둘째 자리</span>
              <input
                type="number"
                min={0.01}
                max={50}
                step={0.01}
                value={draft.take_profit_pct}
                onChange={(e) =>
                  set("take_profit_pct", roundPct2(Number(e.target.value)))
                }
                onBlur={(e) =>
                  set("take_profit_pct", roundPct2(Number(e.target.value)))
                }
              />
            </label>
            <label className="field">
              <span>거래 수수료 (%) · 편도 · 모의</span>
              <input
                type="number"
                min={0}
                max={1}
                step={0.01}
                value={draft.trading_fee_pct ?? 0.05}
                onChange={(e) => set("trading_fee_pct", Number(e.target.value))}
              />
              <small>
                편도 0.05% 기본 · 제안·자동매수·백테스트는 왕복 약 0.10% 반영 · 모의
                체결 시 매수·매도 각각 차감
              </small>
            </label>
            <label className="field">
              <span>시장 스캔 최소 점수</span>
              <input
                type="number"
                min={20}
                max={90}
                value={draft.min_buy_score}
                onChange={(e) => set("min_buy_score", Number(e.target.value))}
              />
            </label>
            <label className="field">
              <span>차트 진입 최소 점수</span>
              <input
                type="number"
                min={40}
                max={90}
                value={draft.min_entry_score}
                onChange={(e) => set("min_entry_score", Number(e.target.value))}
              />
              <small>낮을수록 단타·자동 추천 많음 (기본 38)</small>
            </label>
            <label className="field">
              <span>시장 스캔 주기 (초)</span>
              <input
                type="number"
                min={15}
                max={300}
                value={draft.scan_interval_sec}
                onChange={(e) => set("scan_interval_sec", Number(e.target.value))}
              />
            </label>
            <label className="field">
              <span>최대 보유 종목 (0=무제한)</span>
              <input
                type="number"
                min={0}
                max={30}
                value={draft.max_positions ?? 0}
                onChange={(e) => set("max_positions", Number(e.target.value))}
              />
            </label>
            <label className="field">
              <span>종목당 최대 비중 (%)</span>
              <input
                type="number"
                min={3}
                max={50}
                step={0.5}
                value={draft.max_position_weight_pct ?? 12}
                onChange={(e) =>
                  set("max_position_weight_pct", Number(e.target.value))
                }
              />
            </label>
            <label className="field checkbox-field">
              <input
                type="checkbox"
                checked={draft.trade_hours_enabled ?? true}
                onChange={(e) => set("trade_hours_enabled", e.target.checked)}
              />
              <span>자동 매수 시간대 (KST)</span>
            </label>
            <label className="field">
              <span>시작 시 (0~23)</span>
              <input
                type="number"
                min={0}
                max={23}
                value={draft.trade_start_hour_kst ?? 8}
                onChange={(e) =>
                  set("trade_start_hour_kst", Number(e.target.value))
                }
              />
            </label>
            <label className="field">
              <span>종료 시 (1~24, 미포함)</span>
              <input
                type="number"
                min={1}
                max={24}
                value={draft.trade_end_hour_kst ?? 23}
                onChange={(e) => set("trade_end_hour_kst", Number(e.target.value))}
              />
            </label>
            <label className="field">
              <span>실거래 자동투자 전 모의 검증 일수</span>
              <input
                type="number"
                min={0}
                max={30}
                value={draft.paper_days_before_live_auto ?? 3}
                onChange={(e) =>
                  set("paper_days_before_live_auto", Number(e.target.value))
                }
              />
            </label>
            <label className="field checkbox-field">
              <input
                type="checkbox"
                checked={!!draft.allow_live_auto_invest}
                onChange={(e) => set("allow_live_auto_invest", e.target.checked)}
              />
              <span>실거래 자동투자 허용 (모의 검증 후)</span>
            </label>
          </div>
        </section>

        <section className="settings-section">
          <h3>완전 자동투자 (모의·실거래)</h3>
          <p className="warn subtle">
            상단 「자동 투자 시작」/「실거래 자동 투자」 — 롱·단타 후 스캔·자동 매수·익절/손절.
            실거래는 「실거래 자동투자 허용」 및 API 키 필요.
          </p>
          <div className="field-grid">
            <label className="field">
              <span>스캔당 최대 자동 매수 (건)</span>
              <input
                type="number"
                min={0}
                max={10}
                value={draft.paper_max_auto_buys_per_scan ?? 4}
                onChange={(e) =>
                  set("paper_max_auto_buys_per_scan", Number(e.target.value))
                }
              />
            </label>
            <label className="field">
              <span>스캔당 현금 배분 (%)</span>
              <input
                type="number"
                min={5}
                max={90}
                value={draft.paper_auto_deploy_pct ?? 40}
                onChange={(e) =>
                  set("paper_auto_deploy_pct", Number(e.target.value))
                }
              />
            </label>
            <label className="field">
              <span>일손실 킬 스위치 (%)</span>
              <input
                type="number"
                min={1}
                max={25}
                step={0.5}
                value={draft.daily_loss_limit_pct ?? 5}
                onChange={(e) =>
                  set("daily_loss_limit_pct", Number(e.target.value))
                }
              />
              <small>당일 총자산 하락이 이 %를 넘으면 자동 매수 중지</small>
            </label>
          </div>
        </section>

        <section className="settings-section">
          <h3>백업</h3>
          <p className="panel-hint">
            data 폴더·포지션 메타 백업. API 키는 마스킹되어 포함됩니다.
          </p>
          <div className="settings-actions">
            <a className="btn-secondary" href="/api/backup/export" download>
              백업 ZIP 받기
            </a>
          </div>
        </section>

        {draft.trade_mode === "live" && (
          <section className="settings-section">
            <h3>업비트 Open API</h3>
            <p className="warn subtle">
              시세·스캔·차트·실거래 모두 <strong>업비트 KRW 마켓</strong>만 사용합니다.
            </p>
            <label className="field">
              <span>Access Key</span>
              <input
                type="password"
                value={draft.api_access_key || draft.binance_api_key || ""}
                onChange={(e) => {
                  const v = e.target.value;
                  onChange({
                    ...draft,
                    api_access_key: v,
                    binance_api_key: v,
                  });
                  setTestMsg(null);
                }}
                placeholder={hasSaved ? `저장됨: ${maskedAk}` : "Access Key 입력"}
                autoComplete="off"
              />
            </label>
            <label className="field">
              <span>Secret Key</span>
              <input
                type="password"
                value={draft.api_secret_key || draft.binance_api_secret || ""}
                onChange={(e) => {
                  const v = e.target.value;
                  onChange({
                    ...draft,
                    api_secret_key: v,
                    binance_api_secret: v,
                  });
                  setTestMsg(null);
                }}
                placeholder={hasSaved && maskedSk ? `저장됨: ${maskedSk}` : "Secret Key 입력"}
                autoComplete="off"
              />
            </label>
            {hasSaved && (
              <p className="warn subtle">
                새 API 키 발급 시 Access·Secret <strong>둘 다</strong> 입력 후 [저장] → 연결
                테스트. 빈 칸이면 예전 저장 키가 쓰입니다.
              </p>
            )}
            <div className="modal-actions" style={{ marginTop: 12, padding: 0 }}>
              <button
                type="button"
                className="btn-ghost"
                onClick={handleTest}
                disabled={testing || saving}
              >
                {testing ? "테스트 중..." : "연결 테스트"}
              </button>
            </div>
            {testMsg && (
              <p className={testOk ? "ok-hint" : "warn"} style={{ marginTop: 8 }}>
                {testMsg}
              </p>
            )}
          </section>
        )}

        <section className="settings-section settings-danger">
          <h3>데이터 초기화</h3>
          <p className="warn subtle">
            되돌릴 수 없습니다. 실거래(API) 잔고는 거래소 기준이라 여기서 지우지 않습니다.
          </p>
          <div className="reset-actions">
            <button
              type="button"
              className="btn-danger-outline"
              disabled={!!resetBusy || saving || draft.trade_mode !== "paper"}
              title={
                draft.trade_mode !== "paper"
                  ? "모의투자 모드에서만 사용"
                  : undefined
              }
              onClick={async () => {
                const bal = draft.initial_balance_krw;
                if (
                  !window.confirm(
                    `모의투자를 초기화합니다.\n\n· 보유 코인·거래 내역·실현손익 삭제\n· 현금 ${bal.toLocaleString()}원으로 복구\n· 분석 중이면 중지됩니다\n\n계속할까요?`
                  )
                ) {
                  return;
                }
                setResetBusy("paper");
                try {
                  const s = await resetPaperData();
                  onAfterReset?.(s);
                } catch (e) {
                  alert(e instanceof Error ? e.message : "초기화 실패");
                } finally {
                  setResetBusy(null);
                }
              }}
            >
              {resetBusy === "paper" ? "초기화 중..." : "모의투자 초기화"}
            </button>
            <button
              type="button"
              className="btn-danger-outline"
              disabled={!!resetBusy || saving}
              onClick={async () => {
                if (
                  !window.confirm(
                    "백테스트 누적 데이터를 삭제합니다.\n\n· 종목별 BT 결과·학습 점수·차단 목록\n· 체결 피드백\n\n프로그램을 켜 두면 다시 쌓입니다.\n\n계속할까요?"
                  )
                ) {
                  return;
                }
                setResetBusy("backtest");
                try {
                  const s = await resetBacktestData();
                  onAfterReset?.(s);
                } catch (e) {
                  alert(e instanceof Error ? e.message : "초기화 실패");
                } finally {
                  setResetBusy(null);
                }
              }}
            >
              {resetBusy === "backtest"
                ? "삭제 중..."
                : "백테스트 데이터 초기화"}
            </button>
          </div>
        </section>

        <div className="modal-actions">
          <button type="button" className="btn-ghost wide" onClick={onClose}>
            취소
          </button>
          <button type="button" className="btn-primary" onClick={onSave} disabled={saving}>
            {saving ? "저장 중..." : "저장"}
          </button>
        </div>
      </div>
    </div>
  );
}
