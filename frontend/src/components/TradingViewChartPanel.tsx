import { useMemo } from "react";
import { tvInterval, upbitTvSymbol } from "../utils/chartEngine";

type Props = {
  symbol: string;
  chartInterval: string;
};

function buildEmbedUrl(symbol: string, chartInterval: string): string {
  const iv = chartInterval === "1s" ? "1" : tvInterval(chartInterval);
  const params = new URLSearchParams({
    symbol: upbitTvSymbol(symbol),
    interval: iv,
    timezone: "Asia/Seoul",
    theme: "dark",
    style: "1",
    locale: "kr",
    withdateranges: "1",
    hideideas: "1",
    allow_symbol_change: "0",
    hide_side_toolbar: "0",
    details: "1",
    hotlist: "0",
    calendar: "0",
  });
  return `https://s.tradingview.com/widgetembed/?${params.toString()}`;
}

export default function TradingViewChartPanel({ symbol, chartInterval }: Props) {
  const embedUrl = useMemo(
    () => buildEmbedUrl(symbol, chartInterval),
    [symbol, chartInterval]
  );
  const tvPage = useMemo(
    () =>
      `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(upbitTvSymbol(symbol))}`,
    [symbol]
  );

  return (
    <div className="chart-tv-wrap">
      <iframe
        key={embedUrl}
        className="chart-tv-iframe"
        src={embedUrl}
        title={`TradingView ${upbitTvSymbol(symbol)}`}
        allowFullScreen
        referrerPolicy="no-referrer-when-downgrade"
      />
      <p className="chart-tv-hint">
        업비트 KRW · TradingView ·{" "}
        <a href={tvPage} target="_blank" rel="noopener noreferrer">
          새 탭에서 열기
        </a>
      </p>
    </div>
  );
}
