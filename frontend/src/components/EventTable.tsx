import type { AttackEvent } from "../types";

/**
 * イベント一覧テーブルコンポーネント
 * 収集済みの攻撃イベントを一覧表示し、行クリックで詳細（onSelect）を通知する。
 * 既存 RecentEventsTable のスタイル・構造を踏襲する。
 */
interface EventTableProps {
  /** 表示対象のイベント配列（新しい順で渡される想定） */
  data: AttackEvent[];
  /** データ取得中かどうか */
  loading: boolean;
  /** 行がクリックされたときに対象イベントを通知する（詳細モーダル表示用） */
  onSelect: (event: AttackEvent) => void;
}

export function EventTable({ data, loading, onSelect }: EventTableProps) {
  // ローディング中は取得中である旨を表示する
  if (loading) {
    return (
      <div className="bg-hw-card border border-hw-border rounded-lg p-4">
        <p className="text-gray-400">Loading events...</p>
      </div>
    );
  }

  return (
    <div className="bg-hw-card border border-hw-border rounded-lg p-4">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-400 border-b border-hw-border">
              <th className="text-left py-2 pr-4">Time</th>
              <th className="text-left py-2 pr-4">Source IP</th>
              <th className="text-left py-2 pr-4">Src Port</th>
              <th className="text-left py-2 pr-4">Dst Port</th>
              <th className="text-left py-2 pr-4">Protocol</th>
              <th className="text-left py-2">Event Type</th>
            </tr>
          </thead>
          <tbody>
            {data.length === 0 ? (
              // 0 件時は空状態を表示する（Requirement 1.3）
              <tr>
                <td colSpan={6} className="text-gray-500 py-4 text-center">
                  イベントがありません
                </td>
              </tr>
            ) : (
              data.map((event) => (
                // 各行はクリック可能。行クリックで onSelect を呼び詳細モーダルを開く（Requirement 4.1）
                // アクセシビリティ配慮: button ロールと Enter / Space キー操作、cursor-pointer で操作可能性を明示する
                <tr
                  key={event.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => onSelect(event)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      onSelect(event);
                    }
                  }}
                  aria-label={`イベント詳細を表示: ${event.source_ip} ${event.event_type}`}
                  className="border-b border-hw-border last:border-0 cursor-pointer hover:bg-slate-800/50 focus:bg-slate-800/50 focus:outline-none focus:ring-1 focus:ring-hw-accent"
                >
                  {/* Time: timestamp をローカル日時で表示 */}
                  <td className="py-2 pr-4 text-gray-300 font-mono text-xs">
                    {new Date(event.timestamp).toLocaleString("ja-JP")}
                  </td>
                  {/* Source IP: 等幅フォントで表示 */}
                  <td className="py-2 pr-4 font-mono text-gray-200">
                    {event.source_ip}
                  </td>
                  {/* Src Port: 送信元ポート */}
                  <td className="py-2 pr-4 text-gray-400">
                    {event.source_port}
                  </td>
                  {/* Dst Port: 宛先ポート */}
                  <td className="py-2 pr-4 text-gray-400">
                    {event.destination_port}
                  </td>
                  {/* Protocol: ssh / http でバッジ色分け（既存踏襲） */}
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
                  {/* Event Type: イベントタイプ */}
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
