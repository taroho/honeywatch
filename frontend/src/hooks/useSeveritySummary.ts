import { useEffect, useState } from "react";
import { fetchSeveritySummary } from "../api/client";

/** Severity 別件数 */
interface SeverityCounts {
  HIGH: number;
  MEDIUM: number;
  LOW: number;
}

/**
 * Severity 別集計を取得するカスタムフック
 * 30秒間隔で自動ポーリングする
 */
export function useSeveritySummary(period: string = "24h") {
  const [data, setData] = useState<SeverityCounts>({
    HIGH: 0,
    MEDIUM: 0,
    LOW: 0,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    const load = async () => {
      try {
        const result = await fetchSeveritySummary(period);
        if (mounted) {
          setData(result.severity_summary);
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
