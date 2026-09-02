import { useEffect } from "react";
import type { AttackEvent } from "../types";

/**
 * イベント詳細モーダルコンポーネント
 *
 * 1 件の攻撃イベントの基本情報とリクエスト内容（raw_data）をモーダル表示する。
 * event が null のときは何も描画しない。
 * Esc キー・背景オーバーレイのクリック・閉じるボタンのいずれでも onClose を呼ぶ。
 */
interface EventDetailModalProps {
  /** 表示対象のイベント。null のとき非表示 */
  event: AttackEvent | null;
  /** モーダルを閉じるためのコールバック */
  onClose: () => void;
}

/**
 * raw_data を整形済み JSON 文字列に変換する。
 * - 空/未定義の場合は「リクエスト内容なし」を示す null を返す
 * - JSON 整形に失敗した場合はフォールバック文言を返す
 */
function formatRawData(rawData: Record<string, unknown> | undefined | null): {
  text: string;
  isEmpty: boolean;
} {
  // raw_data が未定義、または中身が空オブジェクトの場合は「リクエスト内容なし」扱い
  if (rawData == null || Object.keys(rawData).length === 0) {
    return { text: "リクエスト内容なし", isEmpty: true };
  }
  try {
    // 整形して等幅フォントで表示できる形にする
    return { text: JSON.stringify(rawData, null, 2), isEmpty: false };
  } catch {
    // 循環参照など整形に失敗した場合のフォールバック
    return { text: "リクエスト内容を表示できません", isEmpty: false };
  }
}

export function EventDetailModal({ event, onClose }: EventDetailModalProps) {
  // Esc キーでモーダルを閉じる。event の有無に応じてリスナーを登録/解除する
  useEffect(() => {
    // event が無いときはリスナーを張らない
    if (!event) {
      return;
    }
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    // クリーンアップでリスナーを必ず解除する
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [event, onClose]);

  // event が null のときは何も表示しない
  if (!event) {
    return null;
  }

  // raw_data を整形（try/catch によるフォールバックは formatRawData 内で処理）
  const { text: rawDataText, isEmpty: rawDataEmpty } = formatRawData(
    event.raw_data,
  );

  // 基本情報の表示項目定義（ラベルと値のペア）
  const infoRows: { label: string; value: string }[] = [
    // timestamp はローカル日時表示に変換
    { label: "Time", value: new Date(event.timestamp).toLocaleString("ja-JP") },
    { label: "Source IP", value: event.source_ip },
    { label: "Source Port", value: String(event.source_port) },
    { label: "Destination Port", value: String(event.destination_port) },
    { label: "Event Type", value: event.event_type },
  ];

  return (
    // 背景オーバーレイ。クリックで閉じる
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
      role="presentation"
    >
      {/* カード本体。内部クリックはオーバーレイへ伝播させない */}
      <div
        className="bg-hw-card border border-hw-border rounded-lg w-full max-w-lg max-h-[85vh] overflow-y-auto shadow-xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Event detail"
      >
        {/* ヘッダー: タイトル + 閉じるボタン */}
        <div className="flex items-center justify-between border-b border-hw-border px-4 py-3">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-medium text-gray-300">Event Detail</h2>
            {/* protocol バッジ（ssh/http で色分け、既存踏襲） */}
            <span
              className={`px-2 py-0.5 rounded text-xs font-medium ${
                event.protocol === "ssh"
                  ? "bg-amber-900/30 text-hw-ssh"
                  : "bg-emerald-900/30 text-hw-http"
              }`}
            >
              {event.protocol.toUpperCase()}
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close event detail"
            className="text-gray-400 hover:text-gray-200 rounded px-2 py-0.5 text-lg leading-none"
          >
            &times;
          </button>
        </div>

        {/* 基本情報 */}
        <div className="px-4 py-3">
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            {infoRows.map((row) => (
              <div key={row.label} className="contents">
                <dt className="text-gray-400">{row.label}</dt>
                <dd className="text-gray-200 font-mono break-all">
                  {row.value}
                </dd>
              </div>
            ))}
          </dl>
        </div>

        {/* リクエスト内容（raw_data） */}
        <div className="border-t border-hw-border px-4 py-3">
          <h3 className="text-xs font-medium text-gray-400 mb-2">
            Request Data
          </h3>
          {rawDataEmpty ? (
            <p className="text-gray-500 text-sm">{rawDataText}</p>
          ) : (
            <pre className="bg-hw-bg border border-hw-border rounded p-3 text-xs text-gray-200 font-mono overflow-x-auto whitespace-pre-wrap break-all">
              {rawDataText}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
