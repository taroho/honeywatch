import { useState } from "react";
import { AuthError, login } from "../api/client";

/**
 * ログインページ
 * Basic 認証の認証情報を入力させ、検証後に Dashboard へ遷移する。
 * 認証情報はコードに埋め込まず、ユーザー入力を localStorage に保持する。
 */
interface LoginPageProps {
  onLoginSuccess: () => void;
}

export function LoginPage({ onLoginSuccess }: LoginPageProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await login(username, password);
      onLoginSuccess();
    } catch (err) {
      if (err instanceof AuthError) {
        setError(err.message);
      } else {
        setError("接続に失敗しました");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-hw-bg flex items-center justify-center p-6">
      <div className="w-full max-w-sm">
        {/* ロゴ */}
        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="w-10 h-10 bg-hw-accent rounded-lg flex items-center justify-center">
            <span className="text-white font-bold text-lg">H</span>
          </div>
          <h1 className="text-2xl font-bold text-gray-100">HoneyWatch</h1>
        </div>

        {/* ログインフォーム */}
        <form
          onSubmit={handleSubmit}
          className="bg-hw-card border border-hw-border rounded-lg p-6 space-y-4"
        >
          <div>
            <label className="block text-sm text-gray-400 mb-1">
              ユーザー名
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full bg-slate-900 border border-hw-border rounded px-3 py-2 text-gray-100 focus:outline-none focus:border-hw-accent"
              autoComplete="username"
              required
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">
              パスワード
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-slate-900 border border-hw-border rounded px-3 py-2 text-gray-100 focus:outline-none focus:border-hw-accent"
              autoComplete="current-password"
              required
            />
          </div>

          {error && <p className="text-sm text-hw-danger">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-hw-accent text-white rounded py-2 font-medium hover:bg-blue-600 disabled:opacity-50 transition-colors"
          >
            {loading ? "認証中..." : "ログイン"}
          </button>
        </form>
      </div>
    </div>
  );
}
