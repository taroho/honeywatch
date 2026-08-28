import { useEffect, useState } from "react";
import { fetchTimeline } from "../api/client";
import type { TimelinePoint } from "../types";

/**
 * タイムラインデータを取得するカスタムフック
 * 30秒間隔で自動ポーリングする
 */
export function useTimeline(period: string = "24h", interval: string = "1h") {
  const [data, setData] = useState<TimelinePoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    const load = async () => {
      try {
        const result = await fetchTimeline(period, interval);
        if (mounted) {
          setData(result.timeline);
          setError(null);
        }
      } catch (e) {
        if (mounted) setError(e instanceof Error ? e.message : "Unknown error");
      } finally {
        if (mounted) setLoading(false);
      }
    };

    load();
    const pollInterval = setInterval(load, 30000);

    return () => {
      mounted = false;
      clearInterval(pollInterval);
    };
  }, [period, interval]);

  return { data, loading, error };
}
