import { useEffect, useState } from "react";
import { fetchCountrySummary } from "../api/client";
import type { CountryCount } from "../types";

/**
 * 国別攻撃件数ランキングを取得するカスタムフック
 *
 * start / end は任意（ISO8601 文字列）。未指定なら全期間を集計対象とする。
 * 国別集計はリアルタイム性が低いが、既存 hook 方針に合わせ 30秒間隔で
 * 自動ポーリングする（useTopIPs と同様）。
 */
export function useCountrySummary(start?: string, end?: string) {
  const [data, setData] = useState<CountryCount[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    const load = async () => {
      try {
        const result = await fetchCountrySummary(start, end);
        if (mounted) {
          setData(result.countries);
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
  }, [start, end]);

  return { data, loading, error };
}
