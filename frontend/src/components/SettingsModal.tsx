import { useState } from "react";
import { testCredentials } from "../api";
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
        if (res.exchange === "upbit") {
          setTestMsg(
            `연결 성공 · KRW ${fmtKrw(res.krw_balance ?? 0)}원 · 보유 코인 ${res.coin_count ?? 0}종`
          );
        } else {
          setTestMsg(res.message || "연결 성공");
        }
      } else {
        setTestOk(false);
        setTestMsg(res.message || "연결 실패");
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
              <span>손절 (%) · 단타</span>
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
              <span>익절 (%) · 단타</span>
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
              <small>낮을수록 단타 진입 많음 (기본 45)</small>
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
            <h3>거래소 API</h3>
            <label className="field">
              <span>거래소</span>
              <select
                value={exchange}
                onChange={(e) => set("exchange", e.target.value)}
              >
                <option value="upbit">업비트 (KRW)</option>
                <option value="binance">Binance (USDT)</option>
              </select>
            </label>
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
                키는 이 PC에만 저장됩니다. 변경 시에만 다시 입력하세요.
              </p>
            )}
            {exchange === "binance" && (
              <label className="field checkbox-field">
                <input
                  type="checkbox"
                  checked={draft.use_testnet}
                  onChange={(e) => set("use_testnet", e.target.checked)}
                />
                <span>Binance 테스트넷 사용 (연습용)</span>
              </label>
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
