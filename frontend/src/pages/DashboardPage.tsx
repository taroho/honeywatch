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
import { CountryRankingTable } from "../components/CountryRankingTable";
import { GeoMap } from "../components/GeoMap";
import { useDashboardSummary } from "../hooks/useDashboardSummary";
import { useTimeline } from "../hooks/useTimeline";
import { useGeoTopIPs } from "../hooks/useGeoTopIPs";
import { useRecentEvents } from "../hooks/useRecentEvents";
import { useAttackTypes } from "../hooks/useAttackTypes";
import { useSeveritySummary } from "../hooks/useSeveritySummary";
import { useRiskRanking } from "../hooks/useRiskRanking";
import { useCountrySummary } from "../hooks/useCountrySummary";

import { clearCredentials } from "../api/client";
import type { View } from "../types";

// 統一期間セレクタの選択肢（Requirement 1.2）
const UNIFIED_PERIOD_OPTIONS = ["1h", "6h", "24h", "7d", "1y", "all"] as const;

/**
 * period を Country_Summary 用の (start, end) ISO8601 範囲に変換する.
 *
 * バックエンドの resolve_period_range と同一の期間定義に揃える。
 * - "all": {}（start/end 未指定＝下限なしの全期間）
 * - それ以外: end = 現在時刻、start = 現在時刻 - 当該期間
 */
function periodToRange(period: string): { start?: string; end?: string } {
  if (period === "all") return {}; // 下限なし＝全期間（start/end 未指定）
  const now = new Date();
  const end = now.toISOString();
  const ms: Record<string, number> = {
    "1h": 3600e3,
    "6h": 6 * 3600e3,
    "24h": 24 * 3600e3,
    "7d": 7 * 24 * 3600e3,
    "1y": 365 * 24 * 3600e3,
  };
  return { start: new Date(now.getTime() - ms[period]).toISOString(), end };
}

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
  // Dashboard 全体の統一集計期間（初期 24h、Requirement 1.3）
  const [period, setPeriod] = useState<string>("24h");

  // ログアウト: 認証情報を破棄してログイン画面へ
  const handleLogout = () => {
    clearCredentials();
    onLogout();
  };

  // Linked_Items: すべて単一 period に連動して集計（Requirement 2.1/2.2）
  const { data: summary, loading: summaryLoading } = useDashboardSummary(period);
  const { data: timeline, loading: timelineLoading } = useTimeline(period);
  // Top IPs は geo 付き（useGeoTopIPs）で地図とテーブルを共用（limit=20, Requirement 6.4/6.6）
  const { data: topIPs, loading: topIPsLoading } = useGeoTopIPs(20, period);

  // Phase 2: 分析データ（期間連動）
  const { data: attackTypes, loading: attackTypesLoading } =
    useAttackTypes(period);
  const { data: severity, loading: severityLoading } =
    useSeveritySummary(period);
  const { data: riskRanking, loading: riskLoading } = useRiskRanking(10, period);

  // Phase 3: 国別攻撃件数ランキング（period → start/end 変換で連動、Requirement 8.1〜8.3）
  const { start, end } = periodToRange(period);
  const { data: countrySummary, loading: countryLoading } = useCountrySummary(
    start,
    end
  );

  // Excluded_Items: Recent Events は period 非連動のまま据え置き（Requirement 2.3）
  const { data: events, loading: eventsLoading } = useRecentEvents(10);

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

        {/* 統一期間セレクタ（Requirement 1.1/1.2/1.4/1.5）。
            ヘッダー直下・サマリーカード直上に単一で配置する。
            Detection Analysis と同一のタブ切り替え方式。 */}
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-lg font-bold text-gray-100">Dashboard</h1>
          <div className="flex gap-1">
            {UNIFIED_PERIOD_OPTIONS.map((opt) => (
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

        {/* サマリーカード (4列)。表題は期間非依存の文言（Requirement 4.4）。 */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <SummaryCard
            title="Attacks"
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
            period={period}
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

        {/* 攻撃元マップ（Geo_Map）。Detection Analysis の直上に全幅で常時表示。
            緯度経度を持つ IP のみマーカー表示する（Requirement 4.7/4.8）。 */}
        <div className="mb-6">
          <GeoMap enabled={true} entries={topIPs} />
        </div>

        {/* === Phase 2: Detection Analysis セクション ===
            期間セレクタは統一セレクタ（ページ上部）に統合済み。見出しのみ残す。 */}
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-bold text-gray-100">
            Detection Analysis
          </h2>
        </div>

        {/* 攻撃タイプ別グラフ + Severity 内訳 (2カラム) */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
          <AttackTypeChart data={attackTypes} loading={attackTypesLoading} />
          <SeverityBreakdown data={severity} loading={severityLoading} />
        </div>

        {/* Risk ランキング + 国別ランキング (2カラム) */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
          <RiskRankingTable data={riskRanking} loading={riskLoading} />
          <CountryRankingTable data={countrySummary} loading={countryLoading} />
        </div>

        {/* 最新イベントテーブル (全幅) */}
        <RecentEventsTable data={events} loading={eventsLoading} />
      </div>
    </div>
  );
}
