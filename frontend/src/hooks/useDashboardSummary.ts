import { useEffect, useState } from "react";
import { fetchDashboardSummary } from "../api/client";
import type { DashboardSummary } from "../types";

/**
 * Dashboard サマリーデータを取得するカスタムフック
 * period で集計期間を指定する（既定 24h）。30秒間隔で自動ポーリングする。
 */
export function useDashboardSummary(period: string = "24h") {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    const load = async () => {
      try {
        const result = await fetchDashboardSummary(period);
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
  }, [period]);

  return { data, loading, error };
}
