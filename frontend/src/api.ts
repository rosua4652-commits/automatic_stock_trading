import type { AppConfig, Candle, StatusPayload } from "./types";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) {
    const text = await r.text();
    throw new Error(text || `HTTP ${r.status}`);
  }
  return r.json();
}

export async function fetchStatus(): Promise<StatusPayload> {
  return request("/api/status");
}

export async function saveConfig(cfg: AppConfig): Promise<StatusPayload> {
  return request("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cfg),
  });
}

export async function startBot(): Promise<StatusPayload> {
  return request("/api/bot/start", { method: "POST" });
}

export async function stopBot(): Promise<StatusPayload> {
  return request("/api/bot/stop", { method: "POST" });
}

export async function fetchChart(
  symbol: string,
  interval: string
): Promise<Candle[]> {
  return request(`/api/chart/${encodeURIComponent(symbol)}?interval=${interval}`);
}

export async function setViewSymbol(symbol: string): Promise<StatusPayload> {
  return request(`/api/view/${encodeURIComponent(symbol)}`, { method: "POST" });
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

  const ping = setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) ws.send("ping");
  }, 25000);

  return () => {
    clearInterval(ping);
    ws.close();
  };
}
