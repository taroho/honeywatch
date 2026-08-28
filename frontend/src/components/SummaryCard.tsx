/**
 * サマリーカードコンポーネント（再利用可能）
 * 数値と説明を表示するカード
 */
interface SummaryCardProps {
  title: string;
  value: number | string;
  color?: string;
}

export function SummaryCard({ title, value, color = "text-gray-100" }: SummaryCardProps) {
  return (
    <div className="bg-hw-card border border-hw-border rounded-lg p-4">
      <p className="text-sm text-gray-400 mb-1">{title}</p>
      <p className={`text-2xl font-bold ${color}`}>
        {typeof value === "number" ? value.toLocaleString() : value}
      </p>
    </div>
  );
}
