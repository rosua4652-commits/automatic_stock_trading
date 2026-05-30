import type {
  AppConfig,
  ChartResponse,
  CredentialsTestResult,
  StatusPayload,
} from "./types";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.headers || {}),
    },
  });
  const text = await r.text();
  if (!r.ok) {
    throw new Error(text || `HTTP ${r.status}`);
  }
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new Error("서버 응답 오류 (HTML 반환됨). 페이지를 새로고침하세요.");
  }
}

export async function fetchStatus(): Promise<StatusPayload> {
  return request("/api/status");
}

export async function saveConfig(cfg: AppConfig): Promise<StatusPayload> {
  const body = {
    ...cfg,
    api_access_key: cfg.api_access_key || cfg.binance_api_key || "",
    api_secret_key: cfg.api_secret_key || cfg.binance_api_secret || "",
  };
  return request("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function testCredentials(cfg: AppConfig): Promise<CredentialsTestResult> {
  const body = {
    ...cfg,
    api_access_key: cfg.api_access_key || cfg.binance_api_key || "",
    api_secret_key: cfg.api_secret_key || cfg.binance_api_secret || "",
  };
  return request("/api/credentials/test", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function startBot(): Promise<StatusPayload> {
  return request("/api/bot/start", { method: "POST" });
}

export async function stopBot(): Promise<StatusPayload> {
  return request("/api/bot/stop", { method: "POST" });
}

export async function applyRecommendations(
  symbols: string[]
): Promise<StatusPayload> {
  return request("/api/recommendations/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbols }),
  });
}

export async function fetchChart(
  symbol: string,
  interval: string
): Promise<ChartResponse> {
  const bust = interval === "1s" || interval === "1m" ? `&_=${Date.now()}` : "";
  return request(
    `/api/chart/${encodeURIComponent(symbol)}?interval=${encodeURIComponent(interval)}${bust}`
  );
}

export async function setViewSymbol(symbol: string): Promise<StatusPayload> {
  return request(`/api/view/${encodeURIComponent(symbol)}`, { method: "POST" });
}

export async function manualBuy(
  symbol: string,
  amount_krw: number
): Promise<StatusPayload> {
  return request("/api/trade/buy", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol, amount_krw }),
  });
}

export async function setPositionExclude(
  symbol: string,
  exclude: boolean
): Promise<StatusPayload> {
  return request(`/api/position/${encodeURIComponent(symbol)}/exclude`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ exclude }),
  });
}

export async function manualSell(
  symbol: string,
  percent: number
): Promise<StatusPayload> {
  return request("/api/trade/sell", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ symbol, percent }),
  });
}

export function connectWs(
  onMessage: (data: StatusPayload) => void,
  onError?: () => void
): () => void {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onmessage = (e) => {
    try {
      onMessage(JSON.parse(e.data));
    } catch {
      onError?.();
    }
  };

  ws.onerror = () => onError?.();

  const pingId = window.setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) ws.send("ping");
  }, 25000);

  return () => {
    window.clearInterval(pingId);
    ws.close();
  };
}
