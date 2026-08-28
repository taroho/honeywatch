import { Header } from "../components/Header";
import { SummaryCard } from "../components/SummaryCard";
import { AttackTimeline } from "../components/AttackTimeline";
import { TopIPsTable } from "../components/TopIPsTable";
import { ProtocolChart } from "../components/ProtocolChart";
import { RecentEventsTable } from "../components/RecentEventsTable";
import { useDashboardSummary } from "../hooks/useDashboardSummary";
import { useTimeline } from "../hooks/useTimeline";
import { useTopIPs } from "../hooks/useTopIPs";
import { useRecentEvents } from "../hooks/useRecentEvents";

/**
 * Dashboard ページ
 * 全コンポーネントを組み合わせてレイアウトする
 */
export function DashboardPage() {
  const { data: summary, loading: summaryLoading } = useDashboardSummary();
  const { data: timeline, loading: timelineLoading } = useTimeline();
  const { data: topIPs, loading: topIPsLoading } = useTopIPs();
  const { data: events, loading: eventsLoading } = useRecentEvents(10);

  return (
    <div className="min-h-screen bg-hw-bg p-6">
      <div className="max-w-7xl mx-auto">
        {/* ヘッダー */}
        <Header />

        {/* サマリーカード (4列) */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <SummaryCard
            title="Attacks Today"
            value={summary?.attacks_today ?? 0}
            color="text-white"
          />
          <SummaryCard
            title="Unique IPs"
            value={summary?.unique_ips_today ?? 0}
            color="text-hw-accent"
          />
          <SummaryCard
            title="SSH Attempts"
            value={summary?.ssh_attempts_today ?? 0}
            color="text-hw-ssh"
          />
          <SummaryCard
            title="HTTP Attacks"
            value={summary?.http_attacks_today ?? 0}
            color="text-hw-http"
          />
        </div>

        {/* タイムライン (全幅) */}
        <div className="mb-6">
          <AttackTimeline data={timeline} loading={timelineLoading || summaryLoading} />
        </div>

        {/* Top IPs + Protocol Chart (2カラム) */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
          <TopIPsTable data={topIPs} loading={topIPsLoading} />
          <ProtocolChart
            sshCount={summary?.ssh_attempts_today ?? 0}
            httpCount={summary?.http_attacks_today ?? 0}
            loading={summaryLoading}
          />
        </div>

        {/* 最新イベントテーブル (全幅) */}
        <RecentEventsTable data={events} loading={eventsLoading} />
      </div>
    </div>
  );
}
