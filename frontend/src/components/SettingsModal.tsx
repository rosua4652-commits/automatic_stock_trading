import type { AppConfig } from "../types";
import { fmtKrw } from "../utils";

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
  const set = <K extends keyof AppConfig>(key: K, value: AppConfig[K]) => {
    onChange({ ...draft, [key]: value });
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
              <span>Binance API 필요 · 실제 자금</span>
            </button>
          </div>
          {draft.trade_mode === "live" && (
            <p className="warn">
              실거래는 API 키 설정 후에만 시작됩니다. 소액으로 먼저 테스트하세요.
            </p>
          )}
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
            <label className="field">
              <span>시작 자금 (원)</span>
              <input
                type="number"
                value={draft.initial_balance_krw}
                onChange={(e) => set("initial_balance_krw", Number(e.target.value))}
              />
              <small>포지션 없을 때만 반영 · 현재 {fmtKrw(config.initial_balance_krw)}원</small>
            </label>
          </div>
        </section>

        <section className="settings-section">
          <h3>매매 전략</h3>
          <div className="field-grid">
            <label className="field">
              <span>최대 보유 코인 수</span>
              <input
                type="number"
                min={1}
                max={15}
                value={draft.max_positions}
                onChange={(e) => set("max_positions", Number(e.target.value))}
              />
            </label>
            <label className="field">
              <span>손절 (%)</span>
              <input
                type="number"
                min={1}
                max={25}
                step={0.5}
                value={draft.stop_loss_pct}
                onChange={(e) => set("stop_loss_pct", Number(e.target.value))}
              />
            </label>
            <label className="field">
              <span>익절 (%)</span>
              <input
                type="number"
                min={2}
                max={50}
                step={0.5}
                value={draft.take_profit_pct}
                onChange={(e) => set("take_profit_pct", Number(e.target.value))}
              />
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
              <small>올라갈 패턴일 때만 자동 매수</small>
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

        {draft.trade_mode === "live" && (
          <section className="settings-section">
            <h3>Binance API (실거래)</h3>
            <label className="field">
              <span>API Key</span>
              <input
                type="password"
                value={draft.binance_api_key}
                onChange={(e) => set("binance_api_key", e.target.value)}
                placeholder="입력 시에만 저장"
              />
            </label>
            <label className="field">
              <span>API Secret</span>
              <input
                type="password"
                value={draft.binance_api_secret}
                onChange={(e) => set("binance_api_secret", e.target.value)}
                placeholder="입력 시에만 저장"
              />
            </label>
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
