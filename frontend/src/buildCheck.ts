/** 서버·UI 빌드 호환 (구버전 배너 오탐 방지) */

export type AidiCapabilities = {
  exit_plan_pct?: boolean;
  manual_sl_tp?: boolean;
  small_sell_retry?: boolean;
};

const LEGACY_ONLY = ["upbit-truth", "cost-basis"];

const NEW_MARKERS = [
  "trade-history",
  "trade-fill-fix",
  "pnl-trade-mobile",
  "small-sell",
  "sl-tp",
  "chart-fix",
  "apply-sell",
];

export const REQUIRED_BUILD_HINT = "최신 ZIP + run.bat (프론트 자동 재빌드)";

/** 서버 API 가 손익절·소액매도 등을 지원하는지 */
export function serverHasModernFeatures(
  buildId: string,
  caps?: AidiCapabilities | null
): boolean {
  if (caps?.exit_plan_pct === true) {
    return true;
  }
  const id = buildId.trim();
  if (!id) {
    return false;
  }
  if (LEGACY_ONLY.some((m) => id.includes(m)) && !NEW_MARKERS.some((m) => id.includes(m))) {
    return false;
  }
  if (NEW_MARKERS.some((m) => id.includes(m))) {
    return true;
  }
  return /2026-03-3\d/.test(id);
}

export function isServerBuildNewEnough(
  buildId: string,
  caps?: AidiCapabilities | null
): boolean {
  return serverHasModernFeatures(buildId, caps);
}

/** UI 번들이 서버와 문자열이 달라도 같은 세대면 경고 생략 */
export function isBuildGenerationCompatible(
  serverBuild: string,
  uiBuild: string,
  caps?: AidiCapabilities | null
): boolean {
  if (!serverBuild || !uiBuild) {
    return true;
  }
  if (serverBuild === uiBuild) {
    return true;
  }
  return (
    serverHasModernFeatures(serverBuild, caps) &&
    serverHasModernFeatures(uiBuild, null)
  );
}
