/**
 * HoneyWatch API レスポンス型定義
 */

/** Dashboard サマリー */
export interface DashboardSummary {
  attacks_today: number;
  unique_ips_today: number;
  ssh_attempts_today: number;
  http_attacks_today: number;
  period_start: string;
  period_end: string;
}

/** タイムラインデータポイント */
export interface TimelinePoint {
  timestamp: string;
  total: number;
  ssh: number;
  http: number;
}

/** タイムラインレスポンス */
export interface TimelineResponse {
  timeline: TimelinePoint[];
}

/** Top IP エントリ */
export interface TopIPEntry {
  source_ip: string;
  event_count: number;
  first_seen: string;
  last_seen: string;
}

/** Top IPs レスポンス */
export interface TopIPsResponse {
  ips: TopIPEntry[];
}

/** 攻撃イベント */
export interface AttackEvent {
  id: string;
  timestamp: string;
  source_ip: string;
  source_port: number;
  destination_port: number;
  protocol: "ssh" | "http";
  event_type: string;
  raw_data: Record<string, unknown>;
}

/** ページネーション情報 */
export interface Pagination {
  page: number;
  per_page: number;
  total: number;
  total_pages: number;
}

/** イベント一覧レスポンス */
export interface EventsResponse {
  events: AttackEvent[];
  pagination: Pagination;
}

/** ヘルスチェックレスポンス */
export interface HealthResponse {
  status: "healthy" | "degraded";
  components: Record<string, "up" | "down">;
}

// === Phase 2: 分析系の型 ===

/** 攻撃タイプ別集計エントリ */
export interface AttackTypeCount {
  attack_type: string;
  count: number;
}

/** 攻撃タイプ別集計レスポンス */
export interface AttackTypesResponse {
  attack_types: AttackTypeCount[];
}

/** Severity 別集計レスポンス */
export interface SeveritySummaryResponse {
  severity_summary: {
    HIGH: number;
    MEDIUM: number;
    LOW: number;
  };
}

/** Risk ランキングエントリ */
export interface RiskRankingEntry {
  source_ip: string;
  risk_score: number;
  risk_level: "HIGH" | "MEDIUM" | "LOW";
  total_events: number;
  attack_types: string[];
}

/** Risk ランキングレスポンス */
export interface RiskRankingResponse {
  ranking: RiskRankingEntry[];
}

// === Phase 3: イベント一覧のフィルタ型 ===

/**
 * イベント一覧の絞り込み条件。
 * すべて任意で、指定されたフィールドのみ API のクエリに付与する。
 * 既存の EventsResponse / AttackEvent / Pagination には影響しない（後方互換）。
 */
export interface EventListFilters {
  /** プロトコル種別（ssh / http）。未指定なら全プロトコル対象 */
  protocol?: "ssh" | "http";
  /** 送信元 IP。未指定なら全 IP 対象 */
  source_ip?: string;
  /** 期間の開始日時（ISO8601 文字列） */
  since?: string;
  /** 期間の終了日時（ISO8601 文字列） */
  until?: string;
}

// === Phase 3: GeoIP（地理情報）系の型 ===

/**
 * IP に対応する地理情報。
 * 未解決のフィールド（未登録・プライベート IP・DB 未ロード・不正 IP 等）は null。
 * バックエンド `/geo/*` エンドポイントが返す geo 構造に対応する。
 */
export interface GeoLocation {
  /** ISO 3166-1 alpha-2 形式の国コード（例: JP） */
  country_code: string | null;
  /** 国名 */
  country_name: string | null;
  /** 地域名（subdivision） */
  region: string | null;
  /** 都市名 */
  city: string | null;
  /** 緯度（-90〜90） */
  latitude: number | null;
  /** 経度（-180〜180） */
  longitude: number | null;
}

/**
 * Geo 付き Top IP エントリ。
 * 既存 TopIPEntry を拡張しつつ、geo API では first_seen / last_seen が
 * null になり得るため、当該フィールドを null 許容に上書きする。
 */
export interface GeoTopIPEntry extends Omit<TopIPEntry, "first_seen" | "last_seen"> {
  /** 初回観測日時（ISO8601 文字列、未取得時 null） */
  first_seen: string | null;
  /** 最終観測日時（ISO8601 文字列、未取得時 null） */
  last_seen: string | null;
  /** 送信元 IP の地理情報（未解決は各フィールド null） */
  geo: GeoLocation;
}

/** Geo 付き Top IPs レスポンス */
export interface GeoTopIPsResponse {
  ips: GeoTopIPEntry[];
}

/** 単一 IP の地理情報レスポンス（GET /geo/ips/{source_ip}） */
export interface IpGeoResponse {
  source_ip: string;
  geo: GeoLocation;
}

/** 国別集計の 1 区分（country_code は "UNKNOWN" を含む） */
export interface CountryCount {
  country_code: string;
  count: number;
}

/** 国別集計レスポンス（GET /geo/country-summary） */
export interface CountrySummaryResponse {
  countries: CountryCount[];
}

// === Phase 3: ビュー切替 ===

/**
 * App が出し分けるビューの種別。
 * ルーティングライブラリを使わず、App.tsx の state でこの値を切り替える。
 */
export type View = "dashboard" | "events";
