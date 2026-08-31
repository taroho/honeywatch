/**
 * Severity 別内訳コンポーネント
 * HIGH / MEDIUM / LOW のイベント件数を色分けカードで表示する
 */
interface SeverityBreakdownProps {
  data: { HIGH: number; MEDIUM: number; LOW: number };
  loading: boolean;
}

export function SeverityBreakdown({ data, loading }: SeverityBreakdownProps) {
  if (loading) {
    return (
      <div className="bg-hw-card border border-hw-border rounded-lg p-4">
        <p className="text-gray-400">Loading...</p>
      </div>
    );
  }

  const items = [
    { level: "HIGH", value: data.HIGH, color: "text-hw-danger", bar: "bg-hw-danger" },
    { level: "MEDIUM", value: data.MEDIUM, color: "text-hw-ssh", bar: "bg-hw-ssh" },
    { level: "LOW", value: data.LOW, color: "text-hw-http", bar: "bg-hw-http" },
  ];
  const total = data.HIGH + data.MEDIUM + data.LOW;

  return (
    <div className="bg-hw-card border border-hw-border rounded-lg p-4">
      <h2 className="text-sm font-medium text-gray-300 mb-3">Severity 別内訳</h2>
      <div className="space-y-3">
        {items.map((item) => (
          <div key={item.level}>
            <div className="flex items-center justify-between mb-1">
              <span className={`text-sm font-medium ${item.color}`}>
                {item.level}
              </span>
              <span className="text-sm text-gray-300">{item.value}</span>
            </div>
            {/* 割合バー */}
            <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
              <div
                className={`h-full ${item.bar} rounded-full`}
                style={{
                  width: total > 0 ? `${(item.value / total) * 100}%` : "0%",
                }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
