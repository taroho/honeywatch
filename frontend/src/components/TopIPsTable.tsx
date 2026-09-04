import type { GeoLocation } from "../types";
import { formatCountry } from "../utils/format";

/**
 * TopIPsTable が表示に必要とする最小のエントリ形状。
 *
 * 既存の TopIPEntry（first_seen / last_seen が string）と、geo 付きの
 * GeoTopIPEntry（first_seen / last_seen が string | null）の両方を受けられるよう、
 * 表示に使うフィールドのみを要求し、geo は任意とする（後方互換）。
 */
interface TopIPRow {
  source_ip: string;
  event_count: number;
  /** 送信元 IP の地理情報（任意）。無い・未解決なら「不明」表示 */
  geo?: GeoLocation;
}

/**
 * Top IPs テーブルコンポーネント
 * 攻撃数の多い送信元 IP をランキング表示する。
 *
 * geo を任意で持つエントリを受け付け、geo があれば国表示を付与する。
 * 既存の TopIPEntry[]（geo 無し）呼び出しとも後方互換（geo 無しは「不明」表示）。
 */
interface TopIPsTableProps {
  /** 表示対象の IP エントリ配列。各要素は任意で geo（地理情報）を持てる */
  data: TopIPRow[];
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
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-xs text-gray-500 w-5">
                  {index + 1}.
                </span>
                <span className="text-sm font-mono text-gray-200">
                  {ip.source_ip}
                </span>
                {/* 国表示: geo があれば「国名 (国コード)」、無ければ「不明」（Requirement 4.1, 4.3, 4.4） */}
                <span className="text-xs text-gray-400 truncate">
                  {formatCountry(ip.geo)}
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
