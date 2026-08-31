import { useEffect, useState } from "react";
import { fetchRiskRanking } from "../api/client";
import type { RiskRankingEntry } from "../types";

/**
 * Risk Score ランキングを取得するカスタムフック
 * 30秒間隔で自動ポーリングする
 */
export function useRiskRanking(limit: number = 10, period: string = "24h") {
  const [data, setData] = useState<RiskRankingEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    const load = async () => {
      try {
        const result = await fetchRiskRanking(limit, period);
        if (mounted) {
          setData(result.ranking);
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
  }, [limit, period]);

  return { data, loading, error };
}
