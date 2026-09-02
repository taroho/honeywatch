import { useState } from "react";
import type { EventListFilters } from "../types";

/**
 * イベント一覧のフィルタ入力コンポーネント。
 *
 * protocol（ssh / http / 未指定）・source_ip・期間（開始 / 終了）の
 * 入力 UI を提供する。ローカルの入力 state を保持し、「適用」操作で
 * 空欄を除いた filters を構築して onChange に渡す。「クリア」操作では
 * 入力を初期化したうえで onChange({}) を呼び、全フィルタを解除する。
 *
 * ページのリセット（1 ページ目へ戻す）は親側の setFilters が担うため、
 * ここでは filters を組み立てて通知するだけでよい。
 */
interface EventFiltersProps {
  /** 現在適用中のフィルタ（初期表示・外部リセットの反映に利用） */
  filters: EventListFilters;
  /** 適用 / クリア時に呼ばれるコールバック */
  onChange: (filters: EventListFilters) => void;
}

/** protocol セレクトの選択肢 */
const PROTOCOL_OPTIONS = [
  { value: "", label: "すべて" },
  { value: "ssh", label: "SSH" },
  { value: "http", label: "HTTP" },
] as const;

/**
 * ISO8601 文字列を <input type="datetime-local"> が扱える
 * ローカル日時文字列（YYYY-MM-DDTHH:mm）へ変換する。
 * 不正な値の場合は空文字を返す。
 */
function isoToLocalInput(iso: string | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  // ローカルタイムゾーンでの分単位までを取り出す
  const pad = (n: number) => String(n).padStart(2, "0");
  const yyyy = date.getFullYear();
  const mm = pad(date.getMonth() + 1);
  const dd = pad(date.getDate());
  const hh = pad(date.getHours());
  const mi = pad(date.getMinutes());
  return `${yyyy}-${mm}-${dd}T${hh}:${mi}`;
}

/**
 * <input type="datetime-local"> のローカル日時文字列を
 * ISO8601（UTC）文字列へ変換する。空欄や不正値は undefined を返す。
 */
function localInputToIso(value: string): string | undefined {
  if (!value) return undefined;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return undefined;
  return date.toISOString();
}

export function EventFilters({ filters, onChange }: EventFiltersProps) {
  // ローカル入力 state（適用するまで親には反映しない）
  const [protocol, setProtocol] = useState<string>(filters.protocol ?? "");
  const [sourceIp, setSourceIp] = useState<string>(filters.source_ip ?? "");
  const [since, setSince] = useState<string>(isoToLocalInput(filters.since));
  const [until, setUntil] = useState<string>(isoToLocalInput(filters.until));

  // 「適用」: 空欄を除いた filters を構築して親へ通知する
  const handleApply = () => {
    const next: EventListFilters = {};
    if (protocol === "ssh" || protocol === "http") {
      next.protocol = protocol;
    }
    const trimmedIp = sourceIp.trim();
    if (trimmedIp) {
      next.source_ip = trimmedIp;
    }
    const sinceIso = localInputToIso(since);
    if (sinceIso) {
      next.since = sinceIso;
    }
    const untilIso = localInputToIso(until);
    if (untilIso) {
      next.until = untilIso;
    }
    onChange(next);
  };

  // 「クリア」: ローカル入力を初期化し、全フィルタを解除する（Requirement 3.5）
  const handleClear = () => {
    setProtocol("");
    setSourceIp("");
    setSince("");
    setUntil("");
    onChange({});
  };

  return (
    <div className="bg-hw-card border border-hw-border rounded-lg p-4 mb-4">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleApply();
        }}
        className="flex flex-wrap items-end gap-4"
      >
        {/* プロトコル選択 */}
        <div className="flex flex-col gap-1">
          <label
            htmlFor="filter-protocol"
            className="text-xs font-medium text-gray-400"
          >
            プロトコル
          </label>
          <select
            id="filter-protocol"
            value={protocol}
            onChange={(e) => setProtocol(e.target.value)}
            className="bg-hw-bg border border-hw-border rounded px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:border-hw-accent"
          >
            {PROTOCOL_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {/* 送信元 IP */}
        <div className="flex flex-col gap-1">
          <label
            htmlFor="filter-source-ip"
            className="text-xs font-medium text-gray-400"
          >
            送信元 IP
          </label>
          <input
            id="filter-source-ip"
            type="text"
            value={sourceIp}
            onChange={(e) => setSourceIp(e.target.value)}
            placeholder="例: 203.0.113.10"
            className="bg-hw-bg border border-hw-border rounded px-3 py-1.5 text-sm text-gray-200 font-mono placeholder:text-gray-600 focus:outline-none focus:border-hw-accent"
          />
        </div>

        {/* 期間: 開始日時 */}
        <div className="flex flex-col gap-1">
          <label
            htmlFor="filter-since"
            className="text-xs font-medium text-gray-400"
          >
            開始日時
          </label>
          <input
            id="filter-since"
            type="datetime-local"
            value={since}
            onChange={(e) => setSince(e.target.value)}
            className="bg-hw-bg border border-hw-border rounded px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:border-hw-accent"
          />
        </div>

        {/* 期間: 終了日時 */}
        <div className="flex flex-col gap-1">
          <label
            htmlFor="filter-until"
            className="text-xs font-medium text-gray-400"
          >
            終了日時
          </label>
          <input
            id="filter-until"
            type="datetime-local"
            value={until}
            onChange={(e) => setUntil(e.target.value)}
            className="bg-hw-bg border border-hw-border rounded px-3 py-1.5 text-sm text-gray-200 focus:outline-none focus:border-hw-accent"
          />
        </div>

        {/* 操作ボタン */}
        <div className="flex gap-2">
          <button
            type="submit"
            className="px-3 py-1.5 rounded text-xs font-medium bg-hw-accent text-white hover:opacity-90 transition-opacity"
          >
            適用
          </button>
          <button
            type="button"
            onClick={handleClear}
            className="px-3 py-1.5 rounded text-xs font-medium bg-hw-card text-gray-400 hover:text-gray-200 border border-hw-border"
          >
            クリア
          </button>
        </div>
      </form>
    </div>
  );
}
