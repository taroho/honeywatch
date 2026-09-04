import type { GeoLocation } from "../types";
import { formatCountry } from "../utils/format";
import worldGeoJson from "../assets/world-110m.geojson.json";

/**
 * GeoMap コンポーネント
 *
 * 攻撃元 Source_IP の地理情報を「世界地図上のマーカー」として表示する。
 * Dashboard（Detection Analysis の直上）に常時表示する（Requirement 4.7, 4.8）。
 * マーカーは「固定サイズの芯 + 件数に応じて広がるぼかしハロー」の 2 層で描画する。
 * 芯は位置を正確に示し、攻撃数の多寡はハローの大きさと色（3 段階）で表現する。
 *
 * 設計方針:
 * - 新しい npm 依存は追加しない。世界地図は Natural Earth 由来（public domain）の
 *   110m GeoJSON（src/assets/world-110m.geojson.json）を読み込み、equirectangular
 *   投影で SVG パスへ変換して背景描画する。外部通信・タイル取得は行わない。
 * - 座標系は viewBox 0 0 360 180。経度 -180..180 → x 0..360、緯度 90..-90 → y 0..180。
 *   地図パスとマーカーが同一座標系となるため位置が完全に一致する。
 * - ハローは SVG radialGradient（中心色付き→外周透明）で表現する。
 *
 * 要件:
 * - Requirement 4.7: 緯度経度を持つ Source_IP をマーカーとして表示する。
 * - Requirement 4.8: 緯度経度が存在しない IP はマーカーとして表示しない。
 */

/** GeoMap が表示に必要とする最小のエントリ形状（geo 付き IP を渡せる） */
interface GeoMapEntry {
  source_ip: string;
  event_count: number;
  /** 送信元 IP の地理情報（緯度経度は null になり得る） */
  geo: GeoLocation;
}

interface GeoMapProps {
  /** 表示フラグ。false のときは何も描画しない。Dashboard からは常時 true。 */
  enabled: boolean;
  /** 表示対象の geo 付き IP エントリ配列 */
  entries: GeoMapEntry[];
}

/** 緯度経度が確定しているマーカー情報（フィルタ後は非 null 保証） */
interface Marker {
  source_ip: string;
  event_count: number;
  geo: GeoLocation;
  latitude: number;
  longitude: number;
}

/** SVG の座標系（equirectangular）。経度 360 幅 × 緯度 180 高。 */
const MAP_WIDTH = 360;
const MAP_HEIGHT = 180;

/** 芯（位置マーカー）の固定半径。全マーカー共通で件数によらず一定。 */
const CORE_RADIUS = 1.3;

/** ハロー半径の下限・上限（件数に応じてこの範囲で変化する） */
const MIN_HALO_RADIUS = 2.5;
const MAX_HALO_RADIUS = 12.0;

/** 件数の多寡を表す 3 段階の色（低・中・高）。 */
const COLOR_LOW = "#facc15"; // 黄（amber-400 相当）
const COLOR_MID = "#fb923c"; // 橙（orange-400 相当）
const COLOR_HIGH = "#ef4444"; // 赤（red-500 相当）

/** 3 段階のレベル種別。radialGradient の id 振り分けにも使う。 */
type Level = "low" | "mid" | "high";

/** レベル → 色 の対応 */
const LEVEL_COLOR: Record<Level, string> = {
  low: COLOR_LOW,
  mid: COLOR_MID,
  high: COLOR_HIGH,
};

/** レベル → ハロー用グラデ id の対応 */
const LEVEL_GRADIENT_ID: Record<Level, string> = {
  low: "halo-low",
  mid: "halo-mid",
  high: "halo-high",
};

/** 経度緯度 [lng, lat] を SVG 座標へ変換する（x = lng+180, y = 90-lat） */
function project(lng: number, lat: number): [number, number] {
  return [lng + 180, 90 - lat];
}

/**
 * GeoJSON の 1 ポリゴンリングを SVG パス片へ変換する。
 * 先頭を M、以降を L で結び、Z で閉じる。
 */
function ringToPath(ring: number[][]): string {
  const commands = ring.map(([lng, lat], index) => {
    const [x, y] = project(lng, lat);
    const cmd = index === 0 ? "M" : "L";
    return `${cmd}${x.toFixed(2)} ${y.toFixed(2)}`;
  });
  return `${commands.join(" ")} Z`;
}

/**
 * GeoJSON FeatureCollection 全体を 1 本の SVG パス文字列へ変換する。
 * Polygon / MultiPolygon の両方に対応する。
 * モジュールロード時に一度だけ計算し、再レンダーごとの再計算を避ける。
 */
const WORLD_PATH: string = (() => {
  const parts: string[] = [];
  const features = (worldGeoJson as { features: Array<{ geometry: { type: string; coordinates: unknown } }> }).features;

  for (const feature of features) {
    const { type, coordinates } = feature.geometry;
    if (type === "Polygon") {
      for (const ring of coordinates as number[][][]) {
        parts.push(ringToPath(ring));
      }
    } else if (type === "MultiPolygon") {
      for (const polygon of coordinates as number[][][][]) {
        for (const ring of polygon) {
          parts.push(ringToPath(ring));
        }
      }
    }
  }
  return parts.join(" ");
})();

/**
 * 件数からハロー半径を算出する。
 * 平方根スケールで件数差を緩やかに反映し、
 * MIN_HALO_RADIUS〜MAX_HALO_RADIUS にクランプする。
 * maxCount は現在表示中の最大件数（相対スケールの基準）。
 * 芯は固定サイズなので、攻撃数の大きさはこのハロー半径で表現する。
 */
function haloRadiusFor(count: number, maxCount: number): number {
  if (maxCount <= 0) {
    return MIN_HALO_RADIUS;
  }
  const ratio = Math.sqrt(count / maxCount);
  return MIN_HALO_RADIUS + ratio * (MAX_HALO_RADIUS - MIN_HALO_RADIUS);
}

/**
 * 件数からレベル（低・中・高）を算出する。
 * 現在表示中の最大件数に対する相対比率で 3 段階に分ける。
 */
function levelFor(count: number, maxCount: number): Level {
  if (maxCount <= 0) {
    return "low";
  }
  const ratio = count / maxCount;
  if (ratio >= 0.66) {
    return "high";
  }
  if (ratio >= 0.33) {
    return "mid";
  }
  return "low";
}

export function GeoMap({ enabled, entries }: GeoMapProps) {
  // enabled が false の間は何も表示しない
  if (!enabled) {
    return null;
  }

  // 緯度経度を持つエントリのみをマーカー対象とする（Requirement 4.8: 無いものは除外）
  const markers: Marker[] = entries
    .filter(
      (entry): entry is GeoMapEntry & { geo: GeoLocation } =>
        entry.geo.latitude != null && entry.geo.longitude != null
    )
    .map((entry) => ({
      source_ip: entry.source_ip,
      event_count: entry.event_count,
      geo: entry.geo,
      latitude: entry.geo.latitude as number,
      longitude: entry.geo.longitude as number,
    }));

  // ハローサイズ・色の相対スケールの基準となる最大件数
  const maxCount = markers.reduce(
    (max, marker) => Math.max(max, marker.event_count),
    0
  );

  return (
    <div className="bg-hw-card border border-hw-border rounded-lg p-4">
      <h2 className="text-sm font-medium text-gray-300 mb-3">攻撃元マップ</h2>
      <div className="relative w-full aspect-[2/1] bg-slate-900 rounded overflow-hidden">
        <svg
          viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`}
          preserveAspectRatio="none"
          className="absolute inset-0 h-full w-full"
        >
          {/* ハロー用の放射状グラデーション定義（中心は色付き→外周は透明）。
              低・中・高の 3 色分を用意し、各マーカーのハローが参照する。 */}
          <defs>
            {(Object.keys(LEVEL_GRADIENT_ID) as Level[]).map((level) => (
              <radialGradient key={level} id={LEVEL_GRADIENT_ID[level]}>
                {/* 中心: ほどよく色付き */}
                <stop offset="0%" stopColor={LEVEL_COLOR[level]} stopOpacity={0.55} />
                {/* 中間 */}
                <stop offset="60%" stopColor={LEVEL_COLOR[level]} stopOpacity={0.2} />
                {/* 外周: 完全透明でぼかす */}
                <stop offset="100%" stopColor={LEVEL_COLOR[level]} stopOpacity={0} />
              </radialGradient>
            ))}
          </defs>

          {/* 世界地図（Natural Earth 110m, public domain）を塗りで描画 */}
          <path
            d={WORLD_PATH}
            className="fill-slate-700 stroke-slate-600"
            strokeWidth={0.2}
          />

          {/* 各マーカーを 2 層で描画: 件数で広がるハロー → 固定サイズの芯。
              芯は位置を正確に示し、攻撃数の多寡はハローの大きさと色で表現する。 */}
          {markers.map((marker) => {
            const [x, y] = project(marker.longitude, marker.latitude);
            const haloR = haloRadiusFor(marker.event_count, maxCount);
            const level = levelFor(marker.event_count, maxCount);
            const color = LEVEL_COLOR[level];
            const title = `${marker.source_ip} / ${formatCountry(marker.geo)} / ${marker.event_count.toLocaleString()}件`;
            return (
              <g key={marker.source_ip}>
                {/* 外周ハロー: 件数に応じて広がる。中心濃く外側透明。 */}
                <circle
                  cx={x}
                  cy={y}
                  r={haloR}
                  fill={`url(#${LEVEL_GRADIENT_ID[level]})`}
                >
                  <title>{title}</title>
                </circle>
                {/* 芯: 固定サイズのくっきりした円で正確な位置を示す */}
                <circle cx={x} cy={y} r={CORE_RADIUS} fill={color} fillOpacity={0.95}>
                  <title>{title}</title>
                </circle>
              </g>
            );
          })}
        </svg>

        {/* 凡例（件数の多寡と色の対応）。右下に小さく表示する。 */}
        <div className="absolute bottom-2 right-2 flex items-center gap-2 rounded bg-slate-800/80 px-2 py-1 text-[10px] text-gray-300">
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: COLOR_LOW }} />
            少
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: COLOR_MID }} />
            中
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: COLOR_HIGH }} />
            多
          </span>
        </div>

        {markers.length === 0 && (
          <p className="absolute inset-0 flex items-center justify-center text-gray-500 text-sm">
            表示できる位置情報がありません
          </p>
        )}
      </div>
    </div>
  );
}
