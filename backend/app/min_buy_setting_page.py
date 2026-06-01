"""최소 매수 금액 — React 없이 브라우저에서 바로 설정 (구버전 UI 대비)."""

from __future__ import annotations

MIN_BUY_SETTING_PATH = "/min-buy-setting"

MIN_BUY_SETTING_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AIDI — 최소 매수 금액</title>
  <style>
    body { font-family: "Malgun Gothic", sans-serif; background: #0f172a; color: #e2e8f0;
      margin: 0; padding: 1.5rem; line-height: 1.5; }
    .box { max-width: 420px; margin: 0 auto; padding: 1.25rem 1.5rem;
      border: 2px solid #38bdf8; border-radius: 12px; background: #1e293b; }
    h1 { font-size: 1.2rem; margin: 0 0 0.5rem; color: #7dd3fc; }
    label { display: block; margin: 1rem 0 0.35rem; font-size: 0.9rem; }
    input { width: 100%; box-sizing: border-box; padding: 0.65rem;
      font-size: 1.1rem; border-radius: 8px; border: 1px solid #475569; background: #0f172a; color: #fff; }
    button { margin-top: 1rem; width: 100%; padding: 0.75rem; font-size: 1rem;
      border: none; border-radius: 8px; background: #2563eb; color: #fff; cursor: pointer; }
    button:disabled { opacity: 0.5; }
    .hint { font-size: 0.85rem; color: #94a3b8; margin-top: 0.75rem; }
    .ok { color: #4ade80; margin-top: 0.75rem; }
    .err { color: #f87171; margin-top: 0.75rem; }
    a { color: #38bdf8; }
    .meta { font-size: 0.8rem; color: #64748b; margin-top: 1rem; }
  </style>
</head>
<body>
  <div class="box">
    <h1>건당 최소 매수 금액</h1>
    <p class="hint">자동투자·승인 매수에 적용. 수동 매수는 업비트 하한 <strong>5,000원</strong>부터.</p>
    <p class="meta" id="build">불러오는 중…</p>
    <label for="amt">금액 (원, 1,000원 단위)</label>
    <input id="amt" type="number" min="5000" max="5000000" step="1000" />
    <button id="save" type="button">저장</button>
    <p id="msg"></p>
    <p class="hint"><a href="/">← AIDI 메인</a></p>
  </div>
  <script>
    const amt = document.getElementById("amt");
    const msg = document.getElementById("msg");
    const build = document.getElementById("build");
    const saveBtn = document.getElementById("save");

    function floorKrw(n) {
      return Math.max(5000, Math.round(Number(n) / 1000) * 1000);
    }

    async function load() {
      try {
        const st = await fetch("/api/status").then(r => r.json());
        const v = st.config && st.config.min_buy_krw;
        amt.value = floorKrw(v > 0 ? v : 6000);
        const b = st.aidi_build || "";
        build.textContent = "서버 빌드: " + (b || "(없음)");
        if (b && !b.includes("min-buy")) {
          build.textContent += " · 구버전 — update-zip.bat 후 run.bat";
        }
      } catch (e) {
        build.textContent = "상태 조회 실패 — run.bat 실행 중인지 확인";
        amt.value = 6000;
      }
    }

    saveBtn.onclick = async () => {
      msg.className = "";
      msg.textContent = "";
      saveBtn.disabled = true;
      const krw = floorKrw(amt.value);
      amt.value = krw;
      try {
        const r = await fetch("/api/config/min-buy-krw", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ min_buy_krw: krw }),
        });
        const j = await r.json();
        if (!r.ok) throw new Error(j.detail || j.message || "저장 실패");
        msg.className = "ok";
        msg.textContent = "저장됨: " + krw.toLocaleString("ko-KR") + "원 · 메인 화면 새로고침(Ctrl+F5)";
      } catch (e) {
        msg.className = "err";
        msg.textContent = e.message || String(e);
      } finally {
        saveBtn.disabled = false;
      }
    };

    load();
  </script>
</body>
</html>
"""
