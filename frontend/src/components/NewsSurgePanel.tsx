import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchNewsFeed, refreshNews } from "../api";
import type { NewsFeedFilter, NewsFeedItem, NewsFeedResponse } from "../types";
import { fmtPublishedTime } from "../utils";
import NewsHeadlineLink from "./NewsHeadlineLink";

type Props = {
  onSelectSymbol?: (symbol: string) => void;
  /** 최근 스캔 moonshot tier — status API */
  surgeSymbols?: string[];
  autoInvestActive?: boolean;
  autoInvestLong?: boolean;
};

function fmtRefreshTs(ts: number): string {
  if (!ts || ts < 1) return "—";
  const d = new Date(ts * 1000);
  return d.toLocaleString("ko-KR", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function filterItems(items: NewsFeedItem[], filter: NewsFeedFilter): NewsFeedItem[] {
  if (filter === "surge") {
    return items.filter((i) => i.tier === "surge" || i.tier === "news_surge");
  }
  if (filter === "downtrend") {
    return items.filter((i) => i.tier === "downtrend");
  }
  return items;
}

export default function NewsSurgePanel({
  onSelectSymbol,
  surgeSymbols = [],
  autoInvestActive = false,
  autoInvestLong = false,
}: Props) {
  const [data, setData] = useState<NewsFeedResponse | null>(null);
  const [filter, setFilter] = useState<NewsFeedFilter>("all");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      let feed = await fetchNewsFeed();
      if (!feed.cache_ok && feed.items.length === 0) {
        feed = await refreshNews();
      }
      setData(feed);
    } catch (e) {
      setError(e instanceof Error ? e.message : "뉴스 목록 불러오기 실패");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleRefresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      const feed = await refreshNews();
      setData(feed);
    } catch (e) {
      setError(e instanceof Error ? e.message : "갱신 실패");
    } finally {
      setRefreshing(false);
    }
  };

  const rows = useMemo(
    () => filterItems(data?.items ?? [], filter),
    [data?.items, filter]
  );

  const surgeSet = useMemo(
    () => new Set(surgeSymbols.map((s) => s.toUpperCase())),
    [surgeSymbols]
  );
  const autoSurgeOn = autoInvestActive && autoInvestLong;

  const llm = data?.llm_status;
  const llmBadge =
    llm?.active === true
      ? "Gemini 활성"
      : llm?.enabled && !llm?.key_configured
        ? "Gemini 키 없음"
        : "키워드만";

  return (
    <div className="news-surge-screen scroll-y">
      <header className="news-surge-head panel-block">
        <div>
          <h2>뉴스 · 급등 · 하락주</h2>
          <p className="panel-hint subtle">
            RSS·CoinGecko·(선택) CryptoPanic 기사 점수와 Gemini AI 방향 판단입니다.
            급등주·뉴스급등·하락주는 기사·LLM 기준으로 분류됩니다.
            {autoSurgeOn && surgeSet.size > 0 && (
              <>
                {" "}
                <strong className="news-auto-hint">
                  롱 자동매수 켜짐 — 스캔 제안 {surgeSet.size}건이 자동매수 후보입니다.
                </strong>
              </>
            )}
            {autoInvestActive && !autoInvestLong && (
              <>
                {" "}
                <span className="warn">
                  단타만 켜짐 — 급등주는 롱 자동매수를 켜야 반영됩니다.
                </span>
              </>
            )}
          </p>
        </div>
        <div className="news-surge-meta">
          <span className={`news-llm-pill ${llm?.active ? "on" : ""}`}>{llmBadge}</span>
          <span className="news-refresh-ts">
            마지막 갱신 {fmtRefreshTs(data?.refreshed_at ?? 0)}
            {!data?.cache_ok && data && " · 캐시 없음(새로고침 권장)"}
          </span>
          <button
            type="button"
            className="btn-secondary"
            disabled={refreshing || loading}
            onClick={handleRefresh}
          >
            {refreshing ? "갱신 중…" : "뉴스 새로고침"}
          </button>
        </div>
      </header>

      <div className="news-filter-tabs">
        <button
          type="button"
          className={filter === "all" ? "active" : ""}
          onClick={() => setFilter("all")}
        >
          전체 {data?.items.length ?? 0}
        </button>
        <button
          type="button"
          className={filter === "surge" ? "active" : ""}
          onClick={() => setFilter("surge")}
        >
          급등주 {data?.surge_count ?? 0}
        </button>
        <button
          type="button"
          className={filter === "downtrend" ? "active" : ""}
          onClick={() => setFilter("downtrend")}
        >
          하락주 {data?.downtrend_count ?? 0}
        </button>
      </div>

      {error && <p className="warn news-surge-error">{error}</p>}
      {loading && !data && <p className="panel-hint">뉴스 데이터 불러오는 중…</p>}
      {!loading && rows.length === 0 && (
        <section className="panel-block empty">
          <p>
            {filter === "all"
              ? "표시할 뉴스 점수가 없습니다. 분석을 켜거나 「뉴스 새로고침」을 눌러 주세요."
              : filter === "surge"
                ? "급등·뉴스급등 분류 종목이 없습니다."
                : "하락주 분류 종목이 없습니다."}
          </p>
        </section>
      )}

      <div className="news-surge-table-wrap">
        <table className="news-surge-table">
          <thead>
            <tr>
              <th>종목</th>
              <th>점수</th>
              <th>AI</th>
              <th>분류</th>
              {autoSurgeOn && <th>자동</th>}
              <th>게시</th>
              <th>헤드라인</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const pub = fmtPublishedTime(row.published_ts ?? 0);
              return (
              <tr
                key={row.symbol}
                className={`tier-${row.tier}`}
                onClick={() => onSelectSymbol?.(row.symbol)}
                role={onSelectSymbol ? "button" : undefined}
                tabIndex={onSelectSymbol ? 0 : undefined}
                onKeyDown={(e) => {
                  if (onSelectSymbol && (e.key === "Enter" || e.key === " ")) {
                    e.preventDefault();
                    onSelectSymbol(row.symbol);
                  }
                }}
              >
                <td>
                  <strong>{row.name_ko}</strong>
                  <span className="news-sym">{row.base}</span>
                </td>
                <td>{row.score.toFixed(1)}</td>
                <td>
                  <span className={`llm-dir ${row.llm_direction || "neutral"}`}>
                    {row.llm_direction_ko || "—"}
                  </span>
                  {row.llm_confidence > 0 && (
                    <small>{row.llm_confidence}%</small>
                  )}
                </td>
                <td>
                  <span className={`news-tier-badge tier-${row.tier}`}>
                    {row.tier_label}
                  </span>
                </td>
                {autoSurgeOn && (
                  <td>
                    {surgeSet.has(row.symbol.toUpperCase()) ? (
                      <span className="news-auto-target-badge" title="롱 자동매수 후보 (스캔 제안 moonshot)">
                        자동매수
                      </span>
                    ) : (
                      <span className="dim">—</span>
                    )}
                  </td>
                )}
                <td className="news-time-cell">
                  <span title={pub.absolute}>{pub.relative}</span>
                  {pub.relative !== pub.absolute && (
                    <small className="news-time-abs">{pub.absolute}</small>
                  )}
                  {row.article_source && (
                    <small className="news-article-src">{row.article_source}</small>
                  )}
                </td>
                <td
                  className="news-headline-cell"
                  onClick={(e) => e.stopPropagation()}
                >
                  <NewsHeadlineLink
                    url={row.url}
                    text={row.headline || row.tag || "—"}
                  />
                  {row.keywords?.length > 0 && (
                    <div className="news-kw">{row.keywords.join(" · ")}</div>
                  )}
                  {row.llm_reason && (
                    <div className="news-llm-reason">{row.llm_reason}</div>
                  )}
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
