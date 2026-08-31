import { useEffect, useState } from "react";
import { fetchAttackTypes } from "../api/client";
import type { AttackTypeCount } from "../types";

/**
 * 攻撃タイプ別集計を取得するカスタムフック
 * 30秒間隔で自動ポーリングする
 */
export function useAttackTypes(period: string = "24h") {
  const [data, setData] = useState<AttackTypeCount[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    const load = async () => {
      try {
        const result = await fetchAttackTypes(period);
        if (mounted) {
          setData(result.attack_types);
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
