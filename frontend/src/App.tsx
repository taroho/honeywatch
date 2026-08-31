import { useState } from "react";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { isAuthenticated } from "./api/client";

function App() {
  // 起動時に localStorage の認証情報有無でログイン状態を判定
  const [authed, setAuthed] = useState<boolean>(isAuthenticated());

  if (!authed) {
    return <LoginPage onLoginSuccess={() => setAuthed(true)} />;
  }

  return <DashboardPage onLogout={() => setAuthed(false)} />;
}

export default App;
