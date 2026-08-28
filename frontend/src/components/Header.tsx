import { useEffect, useState } from "react";

/**
 * ヘッダーコンポーネント
 * ロゴと最終更新時刻を表示する
 */
export function Header() {
  const [lastUpdated, setLastUpdated] = useState<string>("");

  useEffect(() => {
    const update = () => {
      setLastUpdated(new Date().toLocaleTimeString("ja-JP"));
    };
    update();
    const interval = setInterval(update, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <header className="flex items-center justify-between mb-6">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 bg-hw-accent rounded-lg flex items-center justify-center">
          <span className="text-white font-bold text-sm">H</span>
        </div>
        <h1 className="text-xl font-bold text-gray-100">HoneyWatch</h1>
        <span className="text-xs text-gray-500 bg-hw-card px-2 py-0.5 rounded">
          v0.1.0
        </span>
      </div>
      <div className="text-sm text-gray-400">
        Last updated: {lastUpdated}
      </div>
    </header>
  );
}
