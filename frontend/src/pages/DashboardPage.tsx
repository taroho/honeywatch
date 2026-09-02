import { useState } from "react";
import { Header } from "../components/Header";
import { SummaryCard } from "../components/SummaryCard";
import { AttackTimeline } from "../components/AttackTimeline";
import { TopIPsTable } from "../components/TopIPsTable";
import { ProtocolChart } from "../components/ProtocolChart";
import { RecentEventsTable } from "../components/RecentEventsTable";
import { AttackTypeChart } from "../components/AttackTypeChart";
import { SeverityBreakdown } from "../components/SeverityBreakdown";
import { RiskRankingTable } from "../components/RiskRankingTable";
import { useDashboardSummary } from "../hooks/useDashboardSummary";
import { useTimeline } from "../hooks/useTimeline";
import { useTopIPs } from "../hooks/useTopIPs";
import { useRecentEvents } from "../hooks/useRecentEvents";
import { useAttackTypes } from "../hooks/useAttackTypes";
import { useSeveritySummary } from "../hooks/useSeveritySummary";
import { useRiskRanking } from "../hooks/useRiskRanking";

import { clearCredentials } from "../api/client";
import type { View } from "../types";

// 集計期間の選択肢
const PERIOD_OPTIONS = ["1h", "6h", "24h", "7d"] as const;

interface DashboardPageProps {
  onLogout: () => void;
  /** ビュー切替時に呼ばれるコールバック */
  onNavigate: (view: View) => void;
  /** 現在表示中のビュー（ヘッダーのアクティブ表示に利用） */
  currentView: View;
}

/**
 * Dashboard ページ
 * 全コンポーネントを組み合わせてレイアウトする
 */
export function DashboardPage({ onLogout, onNavigate, currentView }: DashboardPageProps) {
  // 分析セクションの集計期間（デフォルトは 7d）
  const [period, setPeriod] = useState<string>("7d");

  // ログアウト: 認証情報を破棄してログイン画面へ
  const handleLogout = () => {
    clearCredentials();
    onLogout();
  };

  const { data: summary, loading: summaryLoading } = useDashboardSummary();
  const { data: timeline, loading: timelineLoading } = useTimeline();
  const { data: topIPs, loading: topIPsLoading } = useTopIPs();
  const { data: events, loading: eventsLoading } = useRecentEvents(10);

  // Phase 2: 分析データ（期間連動）
  const { data: attackTypes, loading: attackTypesLoading } =
    useAttackTypes(period);
  const { data: severity, loading: severityLoading } =
    useSeveritySummary(period);
  const { data: riskRanking, loading: riskLoading } = useRiskRanking(10, period);

  return (
    <div className="min-h-screen bg-hw-bg p-6">
      <div className="max-w-7xl mx-auto">
        {/* ヘッダー + ログアウト */}
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <Header currentView={currentView} onNavigate={onNavigate} />
          </div>
          <button
            onClick={handleLogout}
            className="ml-4 px-3 py-1 rounded text-xs font-medium bg-hw-card text-gray-400 hover:text-gray-200 border border-hw-border"
          >
            ログアウト
          </button>
        </div>

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
          <AttackTimeline
            data={timeline}
            loading={timelineLoading || summaryLoading}
          />
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

        {/* === Phase 2: Detection Analysis セクション === */}
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-bold text-gray-100">
            Detection Analysis
          </h2>
          {/* 期間セレクタ */}
          <div className="flex gap-1">
            {PERIOD_OPTIONS.map((opt) => (
              <button
                key={opt}
                onClick={() => setPeriod(opt)}
                className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                  period === opt
                    ? "bg-hw-accent text-white"
                    : "bg-hw-card text-gray-400 hover:text-gray-200"
                }`}
              >
                {opt}
              </button>
            ))}
          </div>
        </div>

        {/* 攻撃タイプ別グラフ + Severity 内訳 (2カラム) */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
          <AttackTypeChart data={attackTypes} loading={attackTypesLoading} />
          <SeverityBreakdown data={severity} loading={severityLoading} />
        </div>

        {/* Risk ランキング (全幅) */}
        <div className="mb-6">
          <RiskRankingTable data={riskRanking} loading={riskLoading} />
        </div>

        {/* 最新イベントテーブル (全幅) */}
        <RecentEventsTable data={events} loading={eventsLoading} />
      </div>
    </div>
  );
}
