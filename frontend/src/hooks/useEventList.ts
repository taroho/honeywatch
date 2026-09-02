import { useCallback, useEffect, useState } from "react";
import { AuthError, fetchEvents } from "../api/client";
import type { AttackEvent, EventListFilters, Pagination } from "../types";

/**
 * useEventList フックの返り値.
 */
export interface UseEventListResult {
  events: AttackEvent[];
  pagination: Pagination | null;
  loading: boolean;
  error: string | null;
  page: number;
  filters: EventListFilters;
  /** ページを変更して再取得する */
  setPage: (page: number) => void;
  /** フィルタを更新する（page を 1 にリセットして再取得: Property 2） */
  setFilters: (filters: EventListFilters) => void;
  /** 現在の page / filters で再取得する */
  reload: () => void;
}

/**
 * 攻撃イベント一覧を取得するカスタムフック.
 *
 * page / filters / perPage を保持し、page または filters の変更時に
 * `fetchEvents(page, perPage, filters)` を呼んで events / pagination を更新する。
 * ポーリングは行わず、明示的な操作（setPage / setFilters / reload）で再取得する。
 *
 * - 取得中は loading=true、成功で error=null、失敗で error にメッセージを格納する
 *   （画面はクラッシュさせない: Property 6）
 * - 401 は既存の AuthError を再スローし、呼び出し側の認証処理（ログイン画面へ戻す）に委譲する
 *   （Requirement 6.2）
 *
 * @param perPage 1 ページあたりの取得件数（既定 50）
 */
export function useEventList(perPage: number = 50): UseEventListResult {
  const [page, setPageState] = useState<number>(1);
  const [filters, setFiltersState] = useState<EventListFilters>({});
  const [events, setEvents] = useState<AttackEvent[]>([]);
  const [pagination, setPagination] = useState<Pagination | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // reload 用に再取得を明示的にトリガーするためのカウンタ.
  // page / filters が同じでも値を変えることで useEffect を再実行できる。
  const [reloadToken, setReloadToken] = useState<number>(0);

  useEffect(() => {
    // アンマウント後の状態更新を防ぐためのフラグ
    let mounted = true;

    const load = async () => {
      setLoading(true);
      try {
        const result = await fetchEvents(page, perPage, filters);
        if (mounted) {
          setEvents(result.events);
          setPagination(result.pagination);
          setError(null);
        }
      } catch (e) {
        // 401（認証失敗）は認証処理に委譲するため再スローする。
        // ここで catch せず呼び出し側（ログイン画面への遷移）に伝える。
        if (e instanceof AuthError) {
          throw e;
        }
        // それ以外の障害は error state に格納し、画面をクラッシュさせない（Property 6）
        if (mounted) {
          setError(e instanceof Error ? e.message : "Unknown error");
        }
      } finally {
        if (mounted) setLoading(false);
      }
    };

    load();

    return () => {
      mounted = false;
    };
  }, [page, perPage, filters, reloadToken]);

  // ページを変更して再取得する
  const setPage = useCallback((next: number) => {
    setPageState(next);
  }, []);

  // フィルタ更新時は page を 1 にリセットしてから再取得する（Property 2）
  const setFilters = useCallback((next: EventListFilters) => {
    setPageState(1);
    setFiltersState(next);
  }, []);

  // 現在の page / filters で再取得する
  const reload = useCallback(() => {
    setReloadToken((token) => token + 1);
  }, []);

  return {
    events,
    pagination,
    loading,
    error,
    page,
    filters,
    setPage,
    setFilters,
    reload,
  };
}
