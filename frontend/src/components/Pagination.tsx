import type { Pagination } from "../types";

/**
 * Pagination コンポーネントの Props。
 * 型名 `Pagination`（../types）とコンポーネント名 `Pagination` の衝突を避けるため、
 * Props の型は別名 `PaginationProps` で定義する。
 */
interface PaginationProps {
  /** ページネーション情報。null のときは何も表示しない */
  pagination: Pagination | null;
  /** ページ変更時のコールバック（遷移先のページ番号を渡す） */
  onPageChange: (page: number) => void;
}

/**
 * ページ送り UI。
 * 現在ページ / 総ページ数 / 総件数を表示し、前へ・次へボタンを端で無効化する。
 * （Requirement 2.2, 2.3）
 */
export function Pagination({ pagination, onPageChange }: PaginationProps) {
  // pagination 未取得（初回ロード前など）は何も表示しない
  if (pagination === null) {
    return null;
  }

  const { page, total_pages, total } = pagination;

  // 端のページでは対応するボタンを無効化する
  const isFirstPage = page <= 1;
  const isLastPage = page >= total_pages;

  // ボタン共通スタイル（DashboardPage の期間セレクタを踏襲）。
  // 無効時は操作不可を示すためにカーソルと不透明度を調整する。
  const buttonClass =
    "px-3 py-1 rounded text-xs font-medium transition-colors bg-hw-card " +
    "text-gray-400 hover:text-gray-200 border border-hw-border " +
    "disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:text-gray-400";

  return (
    <div className="flex items-center justify-between mt-4">
      {/* 現在ページ / 総ページ数 / 総件数の表示 */}
      <div className="text-xs text-gray-400">
        Page {page} / {total_pages} (全 {total} 件)
      </div>

      {/* 前へ・次へボタン */}
      <div className="flex gap-1">
        <button
          type="button"
          onClick={() => onPageChange(page - 1)}
          disabled={isFirstPage}
          className={buttonClass}
        >
          前へ
        </button>
        <button
          type="button"
          onClick={() => onPageChange(page + 1)}
          disabled={isLastPage}
          className={buttonClass}
        >
          次へ
        </button>
      </div>
    </div>
  );
}
