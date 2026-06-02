import { useCallback, useEffect, useMemo, useState } from "react";
import { disableSurgeSymbol, enableSurgeSymbol, fetchSurgeManage } from "../api";
import type { SurgeManageItem, SurgeManageResponse } from "../types";
import { fmtExpiryTime, fmtPct, fmtPublishedTime } from "../utils";
import NewsHeadlineLink from "./NewsHeadlineLink";

type Props = {
  onSelectSymbol?: (symbol: string) => void;
};

type Filter = "all" | "surge" | "downtrend" | "disabled";

function filterRows(items: SurgeManageItem[], filter: Filter): SurgeManageItem[] {
  if (filter === "surge") return items.filter((i) => i.tag === "surge" && !i.disabled);
  if (filter === "downtrend") return items.filter((i) => i.tag === "downtrend" && !i.disabled);
  if (filter === "disabled") return items.filter((i) => i.disabled);
  return items.filter((i) => !i.disabled);
}

export default function SurgeManagePanel({ onSelectSymbol }: Props) {
  const [data, setData] = useState<SurgeManageResponse | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [loading, setLoading] = useState(true);
  const [busySym, setBusySym] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const res = await fetchSurgeManage();
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "목록 불러오기 실패");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const rows = useMemo(
    () => filterRows(data?.items ?? [], filter),
    [data?.items, filter]
  );

  const toggleDisabled = async (row: SurgeManageItem) => {
    setBusySym(row.symbol);
    setToast(null);
    try {
      const res = row.disabled
        ? await enableSurgeSymbol(row.symbol)
        : await disableSurgeSymbol(row.symbol);
      setData(res);
      setToast(res.message || (row.disabled ? "재활성" : "비활성"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "처리 실패");
    } finally {
      setBusySym(null);
    }
  };

  return (
    <div className="surge-manage-screen scroll-y">
      <header className="news-surge-head panel-block">
        <div>
          <h2>급등 · 하락 관리</h2>
          <p className="panel-hint subtle">
            스캔·뉴스·AI로 분류된 급등주·하락주입니다. 기사 분류는 설정한 시간 후
            자동 만료되며, 관련 기사가 다시 잡히면 연장됩니다. 오분류는 「비활성」으로
            즉시 제외할 수 있습니다.
          </p>
        </div>
        <div className="news-surge-meta">
          <button type="button" className="btn-secondary" onClick={load} disabled={loading}>
            {loading ? "불러오는 중…" : "새로고침"}
          </button>
        </div>
      </header>

      {toast && <p className="panel-hint ok">{toast}</p>}
      {error && <p className="warn news-surge-error">{error}</p>}

      <div className="news-filter-tabs">
        <button
          type="button"
          className={filter === "all" ? "active" : ""}
          onClick={() => setFilter("all")}
        >
          활성 {(data?.surge_count ?? 0) + (data?.downtrend_count ?? 0)}
        </button>
        <button
          type="button"
          className={filter === "surge" ? "active" : ""}
          onClick={() => setFilter("surge")}
        >
          급등 {data?.surge_count ?? 0}
        </button>
        <button
          type="button"
          className={filter === "downtrend" ? "active" : ""}
          onClick={() => setFilter("downtrend")}
        >
          하락 {data?.downtrend_count ?? 0}
        </button>
        <button
          type="button"
          className={filter === "disabled" ? "active" : ""}
          onClick={() => setFilter("disabled")}
        >
          비활성 {data?.disabled_count ?? 0}
        </button>
      </div>

      {loading && !data && <p className="panel-hint">분류 목록 불러오는 중…</p>}
      {!loading && rows.length === 0 && (
        <section className="panel-block empty">
          <p>
            {filter === "disabled"
              ? "비활성 처리된 종목이 없습니다."
              : "표시할 분류 종목이 없습니다. 분석을 켜거나 스캔 후 새로고침하세요."}
          </p>
        </section>
      )}

      <div className="news-surge-table-wrap">
        <table className="news-surge-table surge-manage-table">
          <thead>
            <tr>
              <th>종목</th>
              <th>분류</th>
              <th>출처</th>
              <th>게시</th>
              <th>만료</th>
              <th>헤드라인</th>
              <th>관리</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const pub = fmtPublishedTime(row.published_ts);
              const exp = fmtExpiryTime(row.expires_at ?? 0);
              return (
                <tr
                  key={row.symbol}
                  className={`tier-${row.tier} ${row.disabled ? "row-disabled" : ""}`}
                >
                  <td>
                    <strong
                      role={onSelectSymbol ? "button" : undefined}
                      tabIndex={onSelectSymbol ? 0 : undefined}
                      onClick={() => onSelectSymbol?.(row.symbol)}
                      onKeyDown={(e) => {
                        if (onSelectSymbol && (e.key === "Enter" || e.key === " ")) {
                          e.preventDefault();
                          onSelectSymbol(row.symbol);
                        }
                      }}
                    >
                      {row.name_ko}
                    </strong>
                    <span className="news-sym">{row.base}</span>
                    {row.change_24h !== 0 && (
                      <small className={row.change_24h >= 0 ? "up" : "down"}>
                        {fmtPct(row.change_24h)}
                      </small>
                    )}
                  </td>
                  <td>
                    <span className={`news-tier-badge tier-${row.tag}`}>
                      {row.tier_label}
                    </span>
                  </td>
                  <td>
                    <span className="surge-source-pill">{row.source}</span>
                    {row.score > 0 && <small>{row.score.toFixed(0)}점</small>}
                  </td>
                  <td className="news-time-cell">
                    <span title={pub.absolute}>{pub.relative}</span>
                    {pub.relative !== pub.absolute && (
                      <small className="news-time-abs">{pub.absolute}</small>
                    )}
                    {row.article_source && (
                      <small className="news-article-src">{row.article_source}</small>
                    )}
                  </td>
                  <td className="news-time-cell">
                    {row.expires_at ? (
                      <>
                        <span title={exp.absolute}>{exp.label}</span>
                        <small className="news-time-abs">{exp.absolute}</small>
                      </>
                    ) : (
                      <span className="dim">가격·스캔</span>
                    )}
                  </td>
                  <td className="news-headline-cell">
                    <NewsHeadlineLink
                      url={row.url}
                      text={row.active_headline || row.headline || "—"}
                    />
                    {row.llm_reason && (
                      <div className="news-llm-reason">{row.llm_reason}</div>
                    )}
                  </td>
                  <td>
                    <button
                      type="button"
                      className={`btn-ghost btn-xs ${row.disabled ? "" : "warn"}`}
                      disabled={busySym === row.symbol}
                      onClick={() => toggleDisabled(row)}
                    >
                      {busySym === row.symbol
                        ? "…"
                        : row.disabled
                          ? "재활성"
                          : "비활성"}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
