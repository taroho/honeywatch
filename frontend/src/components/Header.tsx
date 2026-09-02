import { useEffect, useState } from "react";
import type { View } from "../types";

/**
 * ヘッダーコンポーネント
 * ロゴ・最終更新時刻を表示し、ダッシュボード / イベント一覧のビュー切替ナビゲーションを提供する。
 * DashboardPage / EventListPage の双方で共通利用する。
 */
interface HeaderProps {
  /** 現在表示中のビュー（ナビのアクティブ表示に利用） */
  currentView: View;
  /** ビュー切替時に呼ばれるコールバック */
  onNavigate: (view: View) => void;
}

/** ナビゲーションの項目定義 */
const NAV_ITEMS: { view: View; label: string }[] = [
  { view: "dashboard", label: "Dashboard" },
  { view: "events", label: "Events" },
];

export function Header({ currentView, onNavigate }: HeaderProps) {
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

        {/* ビュー切替ナビゲーション（ルーティングライブラリなし） */}
        <nav className="flex gap-1 ml-4">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.view}
              type="button"
              onClick={() => onNavigate(item.view)}
              aria-current={currentView === item.view ? "page" : undefined}
              className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                currentView === item.view
                  ? "bg-hw-accent text-white"
                  : "bg-hw-card text-gray-400 hover:text-gray-200 border border-hw-border"
              }`}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </div>
      <div className="text-sm text-gray-400">Last updated: {lastUpdated}</div>
    </header>
  );
}
