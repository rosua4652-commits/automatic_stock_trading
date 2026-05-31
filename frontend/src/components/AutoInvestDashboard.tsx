import type { BotState } from "../types";

type Props = {
  bot: BotState;
};

export default function AutoInvestDashboard({ bot }: Props) {
  const rejects = bot.auto_invest_rejects ?? [];
  if (!bot.auto_invest_active && rejects.length === 0) {
    return null;
  }

  return (
    <section className="auto-invest-dashboard">
      <h3 className="auto-invest-dashboard-title">자동투자 진단</h3>
      {bot.auto_buy_paused && (
        <p className="panel-hint warn">신규 자동 매수 일시 중지 중 (스캔·손익절은 계속)</p>
      )}
      {bot.auto_invest_message && (
        <p className="auto-invest-dashboard-summary">{bot.auto_invest_message}</p>
      )}
      {rejects.length > 0 ? (
        <ul className="auto-invest-reject-list">
          {rejects.map((line, i) => (
            <li key={`${i}-${line}`}>{line}</li>
          ))}
        </ul>
      ) : (
        <p className="panel-hint dim">최근 스캔 탈락 사유 없음 (또는 통과 대기)</p>
      )}
    </section>
  );
}
