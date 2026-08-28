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
