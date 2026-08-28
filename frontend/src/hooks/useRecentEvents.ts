import { useEffect, useState } from "react";
import { fetchEvents } from "../api/client";
import type { AttackEvent } from "../types";

/**
 * 最新イベントを取得するカスタムフック
 * 30秒間隔で自動ポーリングする
 */
export function useRecentEvents(perPage: number = 10) {
  const [data, setData] = useState<AttackEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    const load = async () => {
      try {
        const result = await fetchEvents(1, perPage);
        if (mounted) {
          setData(result.events);
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
  }, [perPage]);

  return { data, loading, error };
}
