import { useEffect, useState } from "react";
import { fetchDashboardSummary } from "../api/client";
import type { DashboardSummary } from "../types";

/**
 * Dashboard サマリーデータを取得するカスタムフック
 * 30秒間隔で自動ポーリングする
 */
export function useDashboardSummary() {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    const load = async () => {
      try {
        const result = await fetchDashboardSummary();
        if (mounted) {
          setData(result);
          setError(null);
        }
      } catch (e) {
        if (mounted) setError(e instanceof Error ? e.message : "Unknown error");
      } finally {
        if (mounted) setLoading(false);
      }
    };

    load();
    const interval = setInterval(load, 30000);

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  return { data, loading, error };
}
