import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";

/**
 * プロトコル分布円グラフ
 * SSH / HTTP の割合を表示する
 */
interface ProtocolChartProps {
  sshCount: number;
  httpCount: number;
  loading: boolean;
}

const COLORS = {
  ssh: "#f59e0b",
  http: "#10b981",
};

export function ProtocolChart({
  sshCount,
  httpCount,
  loading,
}: ProtocolChartProps) {
  if (loading) {
    return (
      <div className="bg-hw-card border border-hw-border rounded-lg p-4">
        <p className="text-gray-400">Loading...</p>
      </div>
    );
  }

  const total = sshCount + httpCount;
  const data = [
    { name: "SSH", value: sshCount },
    { name: "HTTP", value: httpCount },
  ];

  return (
    <div className="bg-hw-card border border-hw-border rounded-lg p-4">
      <h2 className="text-sm font-medium text-gray-300 mb-3">
        Protocol Distribution
      </h2>
      {total === 0 ? (
        <p className="text-gray-500 text-sm text-center py-8">No data</p>
      ) : (
        <>
          <ResponsiveContainer width="100%" height={160}>
            <PieChart>
              <Pie
                data={data}
                cx="50%"
                cy="50%"
                innerRadius={40}
                outerRadius={65}
                dataKey="value"
              >
                <Cell fill={COLORS.ssh} />
                <Cell fill={COLORS.http} />
              </Pie>
              <Tooltip
                contentStyle={{
                  backgroundColor: "#1e293b",
                  border: "1px solid #334155",
                  borderRadius: "8px",
                }}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex justify-center gap-6 mt-2">
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-hw-ssh" />
              <span className="text-xs text-gray-400">
                SSH {total > 0 ? Math.round((sshCount / total) * 100) : 0}%
              </span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-3 rounded-full bg-hw-http" />
              <span className="text-xs text-gray-400">
                HTTP {total > 0 ? Math.round((httpCount / total) * 100) : 0}%
              </span>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
