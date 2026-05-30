/** 서버 AIDI_BUILD 가 손익절 %·수동지정 API 를 포함하는지 */

const NEW_ENOUGH_MARKERS = [
  "sl-tp-apply-sell",
  "sl-tp-pct",
  "sl-tp-manual",
  "chart-fix",
] as const;

export const REQUIRED_BUILD_HINT = "sl-tp-apply-sell (또는 sl-tp-pct)";

export function isServerBuildNewEnough(buildId: string): boolean {
  if (!buildId.trim()) return false;
  if (NEW_ENOUGH_MARKERS.some((m) => buildId.includes(m))) return true;
  return /sl-tp/.test(buildId);
}

/** 서버·UI 빌드 문자열이 달라도 같은 기능 세대면 경고 생략 */
export function isBuildGenerationCompatible(
  serverBuild: string,
  uiBuild: string
): boolean {
  if (!serverBuild || !uiBuild) return true;
  if (serverBuild === uiBuild) return true;
  return (
    isServerBuildNewEnough(serverBuild) && isServerBuildNewEnough(uiBuild)
  );
}
