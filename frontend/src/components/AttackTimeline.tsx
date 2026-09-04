import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import type { TimelinePoint } from "../types";

/**
 * 攻撃タイムライン折れ線グラフ
 * 時間帯別の攻撃数を SSH / HTTP で色分けして表示する
 */
interface AttackTimelineProps {
  data: TimelinePoint[];
  loading: boolean;
  /** 選択中の集計期間。1y / all のとき横軸ラベルを年月表示に切り替える */
  period: string;
}

export function AttackTimeline({ data, loading, period }: AttackTimelineProps) {
  if (loading) {
    return (
      <div className="bg-hw-card border border-hw-border rounded-lg p-4 h-64 flex items-center justify-center">
        <p className="text-gray-400">Loading timeline...</p>
      </div>
    );
  }

  // 1y / all は月単位バケットのため横軸を年月（YYYY/MM）で表示する。
  // それ以外は従来どおり時刻（時:分）で表示する。
  const isMonthly = period === "1y" || period === "all";
  const formatted = data.map((point) => {
    const d = new Date(point.timestamp);
    const time = isMonthly
      ? `${d.getFullYear()}/${String(d.getMonth() + 1).padStart(2, "0")}`
      : d.toLocaleTimeString("ja-JP", {
          hour: "2-digit",
          minute: "2-digit",
        });
    return { ...point, time };
  });

  return (
    <div className="bg-hw-card border border-hw-border rounded-lg p-4">
      <h2 className="text-sm font-medium text-gray-300 mb-3">
        Attack Timeline
      </h2>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={formatted}>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
          <XAxis dataKey="time" stroke="#94a3b8" fontSize={11} />
          <YAxis stroke="#94a3b8" fontSize={11} />
          <Tooltip
            contentStyle={{
              backgroundColor: "#1e293b",
              border: "1px solid #334155",
              borderRadius: "8px",
            }}
            labelStyle={{ color: "#e2e8f0" }}
          />
          <Legend />
          <Line
            type="monotone"
            dataKey="total"
            stroke="#3b82f6"
            strokeWidth={2}
            dot={false}
            name="Total"
          />
          <Line
            type="monotone"
            dataKey="ssh"
            stroke="#f59e0b"
            strokeWidth={1.5}
            dot={false}
            name="SSH"
          />
          <Line
            type="monotone"
            dataKey="http"
            stroke="#10b981"
            strokeWidth={1.5}
            dot={false}
            name="HTTP"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
