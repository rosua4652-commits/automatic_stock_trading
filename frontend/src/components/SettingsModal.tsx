import { useState } from "react";
import { testCredentials } from "../api";
import type { AppConfig } from "../types";
import { fmtKrw, roundPct2 } from "../utils";

type Props = {
  config: AppConfig;
  draft: AppConfig;
  onChange: (c: AppConfig) => void;
  onSave: () => void;
  onClose: () => void;
  saving: boolean;
};

export default function SettingsModal({
  config,
  draft,
  onChange,
  onSave,
  onClose,
  saving,
}: Props) {
  const [testing, setTesting] = useState(false);
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
      <div className="modal modal-wide" onClick={(e) => e.stopPropagation()} role="dialog">
        <h2>설정</h2>

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
          <h3>매매 전략</h3>
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
          </div>
        </section>

        {draft.trade_mode === "paper" && (
          <section className="settings-section">
            <h3>모의 완전 자동투자</h3>
            <p className="warn subtle">
              「자동 투자 시작」은 모의투자 전용입니다. 스캔·BT·체결 학습·매수·익절/손절이
              자동으로 동작합니다.
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
        )}

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
