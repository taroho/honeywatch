import { useState } from "react";
import { DashboardPage } from "./pages/DashboardPage";
import { EventListPage } from "./pages/EventListPage";
import { LoginPage } from "./pages/LoginPage";
import { isAuthenticated } from "./api/client";
import type { View } from "./types";

function App() {
  // 起動時に localStorage の認証情報有無でログイン状態を判定
  const [authed, setAuthed] = useState<boolean>(isAuthenticated());
  // 表示中のビュー（ルーティングライブラリなしで切り替える）
  const [view, setView] = useState<View>("dashboard");

  // 未認証時はログイン画面のみを表示する（一覧・ダッシュボードは出さない）
  if (!authed) {
    return <LoginPage onLoginSuccess={() => setAuthed(true)} />;
  }

  const handleLogout = () => setAuthed(false);

  // 認証済み時は view に応じてページを出し分ける
  if (view === "events") {
    return (
      <EventListPage
        onLogout={handleLogout}
        onNavigate={setView}
        currentView={view}
      />
    );
  }

  return (
    <DashboardPage
      onLogout={handleLogout}
      onNavigate={setView}
      currentView={view}
    />
  );
}

export default App;
