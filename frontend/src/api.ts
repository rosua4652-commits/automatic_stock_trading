import type { AppConfig, Candle, StatusPayload } from "./types";

const base = "";

export async function fetchStatus(): Promise<StatusPayload> {
  const r = await fetch(`${base}/api/status`);
  return r.json();
}

export async function saveConfig(cfg: AppConfig): Promise<void> {
  await fetch(`${base}/api/config`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cfg),
  });
}

export async function startBot(): Promise<void> {
  await fetch(`${base}/api/bot/start`, { method: "POST" });
}

export async function stopBot(): Promise<void> {
  await fetch(`${base}/api/bot/stop`, { method: "POST" });
}

export async function fetchChart(
  symbol: string,
  interval: string
): Promise<Candle[]> {
  const r = await fetch(
    `${base}/api/chart/${symbol}?interval=${interval}`
  );
  return r.json();
}

export async function selectSymbol(symbol: string): Promise<void> {
  await fetch(`${base}/api/chart/select/${symbol}`, { method: "POST" });
}

export function connectWs(onMessage: (data: StatusPayload) => void): () => void {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage = (e) => {
    try {
      onMessage(JSON.parse(e.data));
    } catch {
      /* ignore */
    }
  };
  const ping = setInterval(() => {
    if (ws.readyState === WebSocket.OPEN) ws.send("ping");
  }, 25000);
  return () => {
    clearInterval(ping);
    ws.close();
  };
}
