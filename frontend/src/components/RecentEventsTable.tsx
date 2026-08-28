import type { AttackEvent } from "../types";

/**
 * 最新イベントテーブルコンポーネント
 * 最近の攻撃イベントを時系列で表示する
 */
interface RecentEventsTableProps {
  data: AttackEvent[];
  loading: boolean;
}

export function RecentEventsTable({ data, loading }: RecentEventsTableProps) {
  if (loading) {
    return (
      <div className="bg-hw-card border border-hw-border rounded-lg p-4">
        <p className="text-gray-400">Loading events...</p>
      </div>
    );
  }

  return (
    <div className="bg-hw-card border border-hw-border rounded-lg p-4">
      <h2 className="text-sm font-medium text-gray-300 mb-3">
        Recent Events
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-400 border-b border-hw-border">
              <th className="text-left py-2 pr-4">Time</th>
              <th className="text-left py-2 pr-4">IP</th>
              <th className="text-left py-2 pr-4">Port</th>
              <th className="text-left py-2 pr-4">Protocol</th>
              <th className="text-left py-2">Type</th>
            </tr>
          </thead>
          <tbody>
            {data.length === 0 ? (
              <tr>
                <td colSpan={5} className="text-gray-500 py-4 text-center">
                  No events recorded yet
                </td>
              </tr>
            ) : (
              data.map((event) => (
                <tr
                  key={event.id}
                  className="border-b border-hw-border last:border-0 hover:bg-slate-800/50"
                >
                  <td className="py-2 pr-4 text-gray-300 font-mono text-xs">
                    {new Date(event.timestamp).toLocaleTimeString("ja-JP")}
                  </td>
                  <td className="py-2 pr-4 font-mono text-gray-200">
                    {event.source_ip}
                  </td>
                  <td className="py-2 pr-4 text-gray-400">
                    {event.destination_port}
                  </td>
                  <td className="py-2 pr-4">
                    <span
                      className={`px-2 py-0.5 rounded text-xs font-medium ${
                        event.protocol === "ssh"
                          ? "bg-amber-900/30 text-hw-ssh"
                          : "bg-emerald-900/30 text-hw-http"
                      }`}
                    >
                      {event.protocol.toUpperCase()}
                    </span>
                  </td>
                  <td className="py-2 text-gray-400 text-xs">
                    {event.event_type}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
