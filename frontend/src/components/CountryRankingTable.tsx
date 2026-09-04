import type { CountryCount } from "../types";
import { UNKNOWN_COUNTRY_LABEL } from "../utils/format";

/**
 * 国別攻撃件数ランキングテーブル
 *
 * 国コードごとの Attack_Event 件数を降順ランキングで表示する。
 * RiskRankingTable と同じ見た目（bg-hw-card のカード + table）を踏襲する。
 *
 * - 上位最大 20 か国を表示する（Requirement 4.5）。
 * - `country_code` が "UNKNOWN" の区分は「不明」と表示する。
 *   国名は CountryCount に含まれないため、国コードをそのまま表示する。
 * - data が空の場合は集計対象データが無い旨を表示する（Requirement 4.6）。
 */
interface CountryRankingTableProps {
  data: CountryCount[];
  loading: boolean;
}

/** 上位表示件数の上限（Requirement 4.5） */
const MAX_COUNTRIES = 20;

/** 国コードを表示用文字列に整形する（"UNKNOWN" は「不明」） */
function formatCountryCode(countryCode: string): string {
  return countryCode === "UNKNOWN" ? UNKNOWN_COUNTRY_LABEL : countryCode;
}

export function CountryRankingTable({ data, loading }: CountryRankingTableProps) {
  if (loading) {
    return (
      <div className="bg-hw-card border border-hw-border rounded-lg p-4">
        <p className="text-gray-400">Loading...</p>
      </div>
    );
  }

  // 上位最大 20 か国のみ表示する
  const rows = data.slice(0, MAX_COUNTRIES);

  return (
    <div className="bg-hw-card border border-hw-border rounded-lg p-4">
      <h2 className="text-sm font-medium text-gray-300 mb-3">
        国別攻撃件数ランキング
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-gray-400 border-b border-hw-border">
              <th className="text-left py-2 pr-4">#</th>
              <th className="text-left py-2 pr-4">国</th>
              <th className="text-left py-2">件数</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              // 集計対象データが無い場合の表示（Requirement 4.6）
              <tr>
                <td colSpan={3} className="text-gray-500 py-4 text-center">
                  集計対象データがありません
                </td>
              </tr>
            ) : (
              rows.map((entry, index) => (
                <tr
                  key={entry.country_code}
                  className="border-b border-hw-border last:border-0 hover:bg-slate-800/50"
                >
                  <td className="py-2 pr-4 text-gray-500">{index + 1}</td>
                  <td className="py-2 pr-4 text-gray-200">
                    {formatCountryCode(entry.country_code)}
                  </td>
                  <td className="py-2 font-bold text-hw-accent">
                    {entry.count.toLocaleString()}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
