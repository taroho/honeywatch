import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { AttackTypeCount } from "../types";

/**
 * 攻撃タイプ別集計グラフ
 * 攻撃タイプごとのイベント数を横棒グラフで表示する
 */
interface AttackTypeChartProps {
  data: AttackTypeCount[];
  loading: boolean;
}

// 攻撃タイプの表示ラベル
const ATTACK_TYPE_LABELS: Record<string, string> = {
  brute_force: "Brute Force",
  port_scan: "Port Scan",
  http_scan: "HTTP Scan",
  credential_attack: "Credential Attack",
  command_injection: "Command Injection",
  suspicious_request: "Suspicious",
};

export function AttackTypeChart({ data, loading }: AttackTypeChartProps) {
  if (loading) {
    return (
      <div className="bg-hw-card border border-hw-border rounded-lg p-4 h-64 flex items-center justify-center">
        <p className="text-gray-400">Loading...</p>
      </div>
    );
  }

  // 表示用ラベルに変換
  const formatted = data.map((item) => ({
    name: ATTACK_TYPE_LABELS[item.attack_type] ?? item.attack_type,
    count: item.count,
  }));

  return (
    <div className="bg-hw-card border border-hw-border rounded-lg p-4">
      <h2 className="text-sm font-medium text-gray-300 mb-3">攻撃タイプ別集計</h2>
      {formatted.length === 0 ? (
        <p className="text-gray-500 text-sm text-center py-8">No data</p>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={formatted} layout="vertical" margin={{ left: 30 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
            <XAxis type="number" stroke="#94a3b8" fontSize={11} />
            <YAxis
              type="category"
              dataKey="name"
              stroke="#94a3b8"
              fontSize={11}
              width={110}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#1e293b",
                border: "1px solid #334155",
                borderRadius: "8px",
              }}
              labelStyle={{ color: "#e2e8f0" }}
            />
            <Bar dataKey="count" fill="#3b82f6" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
