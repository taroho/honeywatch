import { useState } from "react";
import { Header } from "../components/Header";
import { EventFilters } from "../components/EventFilters";
import { EventTable } from "../components/EventTable";
import { Pagination } from "../components/Pagination";
import { EventDetailModal } from "../components/EventDetailModal";
import { useEventList } from "../hooks/useEventList";
import { clearCredentials } from "../api/client";
import type { AttackEvent, View } from "../types";

/**
 * イベント一覧ページ
 *
 * useEventList フックで取得したイベントを、EventFilters / EventTable /
 * Pagination / EventDetailModal を組み合わせて表示・操作できるようにする。
 *
 * - フィルタ変更・ページ送りはフック（setFilters / setPage）に委譲する。
 *   フィルタ変更時はフック側で 1 ページ目にリセットされる（Property 2）。
 * - 選択中イベントは本ページの state（selectedEvent）で保持し、詳細モーダルを
 *   閉じても一覧のページ・フィルタ状態は維持される（Requirement 4.3）。
 *   詳細は一覧取得時に得た raw_data を表示するだけで、追加の API 呼び出しは行わない
 *   （Property 3）。
 * - 取得エラー時はテーブル上部にエラー領域を表示し、画面はクラッシュさせない
 *   （Requirement 6.1 / Property 6）。
 * - ヘッダー（ビュー切替ナビ）とログアウトは DashboardPage と同じ構成で配置する。
 */
interface EventListPageProps {
  /** ログアウト時に呼ばれるコールバック（認証情報破棄後の画面遷移） */
  onLogout: () => void;
  /** ビュー切替時に呼ばれるコールバック */
  onNavigate: (view: View) => void;
  /** 現在表示中のビュー（ヘッダーのアクティブ表示に利用） */
  currentView: View;
}

export function EventListPage({
  onLogout,
  onNavigate,
  currentView,
}: EventListPageProps) {
  // 一覧取得ロジック（page / filters / perPage を内部で保持）
  const { events, pagination, loading, error, filters, setPage, setFilters } =
    useEventList();

  // 詳細モーダルで表示する選択中イベント。null のときモーダルは非表示。
  // 一覧の page / filters とは独立に保持するため、モーダルを閉じても一覧状態は維持される。
  const [selectedEvent, setSelectedEvent] = useState<AttackEvent | null>(null);

  // ログアウト: 認証情報を破棄してログイン画面へ（DashboardPage と同じ挙動）
  const handleLogout = () => {
    clearCredentials();
    onLogout();
  };

  return (
    <div className="min-h-screen bg-hw-bg p-6">
      <div className="max-w-7xl mx-auto">
        {/* ヘッダー + ログアウト（DashboardPage と同じ構成） */}
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <Header currentView={currentView} onNavigate={onNavigate} />
          </div>
          <button
            onClick={handleLogout}
            className="ml-4 px-3 py-1 rounded text-xs font-medium bg-hw-card text-gray-400 hover:text-gray-200 border border-hw-border"
          >
            ログアウト
          </button>
        </div>

        {/* ページタイトル */}
        <h2 className="text-lg font-bold text-gray-100 mb-4">Event List</h2>

        {/* フィルタ入力。適用 / クリアで setFilters を呼び、page は 1 にリセットされる */}
        <EventFilters filters={filters} onChange={setFilters} />

        {/* 取得エラー時のエラー領域（画面はクラッシュさせない: Requirement 6.1 / Property 6） */}
        {error !== null && (
          <div
            role="alert"
            className="bg-red-900/30 border border-red-800 text-red-300 rounded-lg px-4 py-3 mb-4 text-sm"
          >
            イベントの取得に失敗しました: {error}
          </div>
        )}

        {/* イベント一覧テーブル。行クリックで詳細モーダルを開く */}
        <EventTable
          data={events}
          loading={loading}
          onSelect={setSelectedEvent}
        />

        {/* ページ送り UI（pagination が null の間は非表示） */}
        <Pagination pagination={pagination} onPageChange={setPage} />

        {/* 詳細モーダル。閉じると selectedEvent を null に戻す（一覧状態は維持） */}
        <EventDetailModal
          event={selectedEvent}
          onClose={() => setSelectedEvent(null)}
        />
      </div>
    </div>
  );
}
