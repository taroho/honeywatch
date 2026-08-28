/**
 * HoneyWatch API クライアント
 *
 * Basic Auth 付きの fetch ベース API クライアント。
 * 開発時は Vite の proxy 経由で API サーバーに接続する。
 */

import type {
  DashboardSummary,
  EventsResponse,
  TimelineResponse,
  TopIPsResponse,
} from "../types";

// API Base URL（Vite proxy 経由なので相対パス）
const API_BASE = "/api/v1";

// Basic Auth 認証情報（開発用デフォルト値）
// 本番環境ではログインフォームから取得する
const API_USER = "admin";
const API_PASSWORD = "changeme";

/**
 * 認証ヘッダー付きの fetch ラッパー
 */
async function fetchWithAuth(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  const credentials = btoa(`${API_USER}:${API_PASSWORD}`);

  const response = await fetch(url, {
    ...options,
    headers: {
      ...options.headers,
      Authorization: `Basic ${credentials}`,
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    throw new Error(`API Error: ${response.status} ${response.statusText}`);
  }

  return response;
}

/** Dashboard サマリーを取得する */
export async function fetchDashboardSummary(): Promise<DashboardSummary> {
  const response = await fetchWithAuth(`${API_BASE}/dashboard/summary`);
  return response.json();
}

/** タイムラインデータを取得する */
export async function fetchTimeline(
  period: string = "24h",
  interval: string = "1h"
): Promise<TimelineResponse> {
  const params = new URLSearchParams({ period, interval });
  const response = await fetchWithAuth(
    `${API_BASE}/dashboard/timeline?${params}`
  );
  return response.json();
}

/** Top IPs ランキングを取得する */
export async function fetchTopIPs(
  limit: number = 10,
  period: string = "24h"
): Promise<TopIPsResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    period,
  });
  const response = await fetchWithAuth(
    `${API_BASE}/dashboard/top-ips?${params}`
  );
  return response.json();
}

/** イベント一覧を取得する */
export async function fetchEvents(
  page: number = 1,
  perPage: number = 20
): Promise<EventsResponse> {
  const params = new URLSearchParams({
    page: String(page),
    per_page: String(perPage),
  });
  const response = await fetchWithAuth(`${API_BASE}/events?${params}`);
  return response.json();
}
