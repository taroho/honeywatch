import type { RiskRankingEntry } from "../types";

/**
 * Risk Score ランキングテーブル
 * 危険度の高い送信元 IP を Risk Score 順に表示する
 */
interface RiskRankingTableProps {
  data: RiskRankingEntry[];
  loading: boolean;
}

// Risk レベルごとの色クラス
const RISK_LEVEL_STYLE: Record<string, string> = {
  HIGH: "bg-red-900/30 text-hw-danger",
  MEDIUM: "bg-amber-900/30 text-hw-ssh",
  LOW: "bg-emerald-900/30 text-hw-http",
};

export function RiskRankingTable({ data, loading }: RiskRankingTableProps) {
  if (loading) {
    return (
      <div className="bg-hw-card border border-hw-border rounded-lg p-4">
        <p className="text-gray-400">Loading...</p>
      </div>
    );
  }

  return (
    <div className="bg-hw-card border border-hw-border rounded-lg p-4">
      <h2 className="text-sm font-medium text-gray-300 mb-3">
        Risk Score ランキング
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-400 border-b border-hw-border">
              <th className="text-left py-2 pr-4">#</th>
              <th className="text-left py-2 pr-4">IP</th>
              <th className="text-left py-2 pr-4">Score</th>
              <th className="text-left py-2 pr-4">Level</th>
              <th className="text-left py-2">Events</th>
            </tr>
          </thead>
          <tbody>
            {data.length === 0 ? (
              <tr>
                <td colSpan={5} className="text-gray-500 py-4 text-center">
                  No data available
                </td>
              </tr>
            ) : (
              data.map((entry, index) => (
                <tr
                  key={entry.source_ip}
                  className="border-b border-hw-border last:border-0 hover:bg-slate-800/50"
                >
                  <td className="py-2 pr-4 text-gray-500">{index + 1}</td>
                  <td className="py-2 pr-4 font-mono text-gray-200">
                    {entry.source_ip}
                  </td>
                  <td className="py-2 pr-4 font-bold text-gray-100">
                    {entry.risk_score}
                  </td>
                  <td className="py-2 pr-4">
                    <span
                      className={`px-2 py-0.5 rounded text-xs font-medium ${
                        RISK_LEVEL_STYLE[entry.risk_level] ?? ""
                      }`}
                    >
                      {entry.risk_level}
                    </span>
                  </td>
                  <td className="py-2 text-gray-400">{entry.total_events}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
