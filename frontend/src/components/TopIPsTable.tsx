import type { TopIPEntry } from "../types";

/**
 * Top IPs テーブルコンポーネント
 * 攻撃数の多い送信元 IP をランキング表示する
 */
interface TopIPsTableProps {
  data: TopIPEntry[];
  loading: boolean;
}

export function TopIPsTable({ data, loading }: TopIPsTableProps) {
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
        Top Source IPs
      </h2>
      <div className="space-y-2">
        {data.length === 0 ? (
          <p className="text-gray-500 text-sm">No data available</p>
        ) : (
          data.map((ip, index) => (
            <div
              key={ip.source_ip}
              className="flex items-center justify-between py-1.5 border-b border-hw-border last:border-0"
            >
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500 w-5">
                  {index + 1}.
                </span>
                <span className="text-sm font-mono text-gray-200">
                  {ip.source_ip}
                </span>
              </div>
              <span className="text-sm font-bold text-hw-accent">
                {ip.event_count.toLocaleString()}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
