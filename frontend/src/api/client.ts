/**
 * HoneyWatch API クライアント
 *
 * Basic Auth 付きの fetch ベース API クライアント。
 * 開発時は Vite の proxy 経由で API サーバーに接続する。
 */

import type {
  AttackTypesResponse,
  DashboardSummary,
  EventListFilters,
  EventsResponse,
  RiskRankingResponse,
  SeveritySummaryResponse,
  TimelineResponse,
  TopIPsResponse,
} from "../types";

// API Base URL（Vite proxy 経由なので相対パス）
const API_BASE = "/api/v1";

// localStorage に認証情報を保持するキー
const CREDENTIALS_KEY = "honeywatch_credentials";

/** 認証エラー（401）を表す例外 */
export class AuthError extends Error {
  constructor(message = "認証に失敗しました") {
    super(message);
    this.name = "AuthError";
  }
}

/**
 * 認証情報（Basic 認証の base64 文字列）を保存する.
 * ユーザー名・パスワードはコードに埋め込まず、実行時に入力された値を保持する。
 */
export function setCredentials(username: string, password: string): void {
  const encoded = btoa(`${username}:${password}`);
  localStorage.setItem(CREDENTIALS_KEY, encoded);
}

/** 保存済みの認証情報を取得する（未ログインなら null）. */
export function getCredentials(): string | null {
  return localStorage.getItem(CREDENTIALS_KEY);
}

/** 認証情報を破棄する（ログアウト）. */
export function clearCredentials(): void {
  localStorage.removeItem(CREDENTIALS_KEY);
}

/** ログイン済みかどうか. */
export function isAuthenticated(): boolean {
  return getCredentials() !== null;
}

/**
 * 認証ヘッダー付きの fetch ラッパー.
 *
 * localStorage に保持された認証情報を使う。
 * 401 の場合は認証情報を破棄して AuthError を投げる。
 */
async function fetchWithAuth(
  url: string,
  options: RequestInit = {}
): Promise<Response> {
  const credentials = getCredentials();
  if (credentials === null) {
    throw new AuthError("未ログインです");
  }

  const response = await fetch(url, {
    ...options,
    headers: {
      ...options.headers,
      Authorization: `Basic ${credentials}`,
      "Content-Type": "application/json",
    },
  });

  if (response.status === 401) {
    // 認証失敗: 保存情報を破棄してログイン画面に戻す
    clearCredentials();
    throw new AuthError();
  }

  if (!response.ok) {
    throw new Error(`API Error: ${response.status} ${response.statusText}`);
  }

  return response;
}

/**
 * 指定した認証情報でログインを試す.
 * health ではなく認証必須エンドポイントを叩いて検証する。
 */
export async function login(username: string, password: string): Promise<void> {
  setCredentials(username, password);
  try {
    // 認証必須エンドポイントで検証
    const encoded = getCredentials();
    const response = await fetch(`${API_BASE}/dashboard/summary`, {
      headers: {
        Authorization: `Basic ${encoded}`,
        "Content-Type": "application/json",
      },
    });
    if (response.status === 401) {
      clearCredentials();
      throw new AuthError("ユーザー名またはパスワードが違います");
    }
    if (!response.ok) {
      throw new Error(`API Error: ${response.status}`);
    }
  } catch (e) {
    if (e instanceof AuthError) throw e;
    clearCredentials();
    throw e;
  }
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

/**
 * イベント一覧を取得する.
 *
 * 第3引数 filters は任意（既定 `{}`）。値が指定された条件のみクエリに付与する。
 * これにより既存の 2 引数呼び出し（useRecentEvents の fetchEvents(1, perPage)）は
 * 挙動が変わらず、後方互換を保つ。
 */
export async function fetchEvents(
  page: number = 1,
  perPage: number = 20,
  filters: EventListFilters = {}
): Promise<EventsResponse> {
  const params = new URLSearchParams({
    page: String(page),
    per_page: String(perPage),
  });
  // フィルタは値がある場合のみ付与する（空文字・undefined は無視）
  if (filters.protocol) params.set("protocol", filters.protocol);
  if (filters.source_ip) params.set("source_ip", filters.source_ip);
  if (filters.since) params.set("since", filters.since);
  if (filters.until) params.set("until", filters.until);
  const response = await fetchWithAuth(`${API_BASE}/events?${params}`);
  return response.json();
}

// === Phase 2: 分析 API ===

/** 攻撃タイプ別集計を取得する */
export async function fetchAttackTypes(
  period: string = "24h"
): Promise<AttackTypesResponse> {
  const params = new URLSearchParams({ period });
  const response = await fetchWithAuth(
    `${API_BASE}/analysis/attack-types?${params}`
  );
  return response.json();
}

/** Severity 別集計を取得する */
export async function fetchSeveritySummary(
  period: string = "24h"
): Promise<SeveritySummaryResponse> {
  const params = new URLSearchParams({ period });
  const response = await fetchWithAuth(
    `${API_BASE}/analysis/severity-summary?${params}`
  );
  return response.json();
}

/** Risk Score ランキングを取得する */
export async function fetchRiskRanking(
  limit: number = 10,
  period: string = "24h"
): Promise<RiskRankingResponse> {
  const params = new URLSearchParams({ limit: String(limit), period });
  const response = await fetchWithAuth(
    `${API_BASE}/analysis/risk-ranking?${params}`
  );
  return response.json();
}
