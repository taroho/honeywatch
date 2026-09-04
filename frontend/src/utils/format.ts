/**
 * 表示用のフォーマットヘルパー群
 *
 * 純粋関数として実装し、テスト・再利用しやすくする。
 */

import type { GeoLocation } from "../types";

/** 地理情報が未解決の場合に表示する固定文言 */
export const UNKNOWN_COUNTRY_LABEL = "不明";

/**
 * 地理情報（GeoLocation）を表示用の国文字列に整形する.
 *
 * 表示ルール（Requirement 4.3, 4.4）:
 * - `geo` が null / undefined、または `country_code` が null の場合は
 *   未解決とみなし固定文言「不明」を返す。
 * - `country_name` があれば `国名 (国コード)` 形式で返す。
 * - `country_name` が null で `country_code` のみある場合は `country_code` を返す。
 *
 * @param geo 対象の地理情報（未解決・未取得は null / undefined）
 * @returns 表示用の国文字列（未解決時は「不明」）
 */
export function formatCountry(
  geo: GeoLocation | null | undefined
): string {
  // 未取得・未解決（country_code なし）は「不明」で表示する
  if (geo == null || geo.country_code == null) {
    return UNKNOWN_COUNTRY_LABEL;
  }
  // 国名があれば「国名 (国コード)」、無ければ国コードのみを表示する
  if (geo.country_name != null) {
    return `${geo.country_name} (${geo.country_code})`;
  }
  return geo.country_code;
}
