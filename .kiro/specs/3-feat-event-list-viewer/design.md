# Design

## Overview

Dashboard に攻撃イベントの一覧画面を追加する。既存の `GET /api/v1/events`（ページネーション・フィルタ対応済み）を利用し、バックエンドは変更しない。フロントエンドは React Router を導入せず、`App.tsx` にビュー切替の state を持たせてダッシュボードと一覧を出し分ける。イベントの詳細（`raw_data` = リクエスト内容）はモーダルで表示する。

### 設計方針

- ルーティングライブラリを追加せず、`App.tsx` の `view` state（`"dashboard" | "events"`）でビューを切り替える
- 既存の `fetchEvents` は `page` / `perPage` のみ対応のため、フィルタ引数（protocol / source_ip / since / until）を渡せるよう拡張する（後方互換を保つ）
- 一覧の取得ロジックはカスタムフック `useEventList` に集約する（既存フックのポーリングとは別に、明示的な操作でリロードする方式）
- 詳細は一覧取得時に得られる `raw_data` をそのままモーダル表示し、追加の API 呼び出しはしない
- 既存 Dashboard のデザイントークン（`hw-bg` / `hw-card` / `hw-border` / `hw-accent` / `hw-ssh` / `hw-http`）と、既存 `RecentEventsTable` のスタイルを踏襲する

## Architecture

フロントエンドのビュー構成を以下のように変更する。

```
                    App.tsx
          （認証状態 + view state を保持）
                       |
        +--------------+---------------+
   未認証 |         認証済み view=dashboard   view=events
        v              v                    v
   LoginPage     DashboardPage         EventListPage  <- NEW
                       |                    |
                 （既存のまま）    +---------+----------+
                                  |                    |
                            EventFilters          EventTable -- 行クリック
                            Pagination                 |
                                                       v
                                              EventDetailModal <- NEW
                                                （raw_data 表示）
```

### データ取得フロー

```
EventListPage
   | (page, filters)
   v
useEventList フック
   | fetchEvents(page, perPage, filters)
   v
api/client.ts  -- GET /api/v1/events?page=&per_page=&protocol=&source_ip=&since=&until=
   v
既存 FastAPI /events エンドポイント（変更なし）
```

## Components and Interfaces

| コンポーネント | 責務 | 配置 |
|--------------|------|------|
| App（拡張） | 認証状態 + ビュー切替 state の管理 | src/App.tsx |
| Header（拡張） | ダッシュボード / 一覧のナビゲーション | src/components/Header.tsx |
| EventListPage | 一覧画面のレイアウト・状態管理 | src/pages/EventListPage.tsx |
| EventFilters | protocol / source_ip / 期間の入力 UI | src/components/EventFilters.tsx |
| EventTable | イベント一覧テーブル（行クリックで詳細） | src/components/EventTable.tsx |
| Pagination | ページ送り UI | src/components/Pagination.tsx |
| EventDetailModal | 1件の詳細（基本情報 + raw_data）をモーダル表示 | src/components/EventDetailModal.tsx |
| useEventList | 一覧取得・ページ・フィルタ状態を管理するフック | src/hooks/useEventList.ts |
| fetchEvents（拡張） | フィルタ引数を受け取れるよう拡張 | src/api/client.ts |

### useEventList フックのインターフェース

```typescript
interface EventListFilters {
  protocol?: "ssh" | "http";
  source_ip?: string;
  since?: string; // ISO8601
  until?: string; // ISO8601
}

interface UseEventListResult {
  events: AttackEvent[];
  pagination: Pagination | null;
  loading: boolean;
  error: string | null;
  page: number;
  filters: EventListFilters;
  setPage: (page: number) => void;
  setFilters: (filters: EventListFilters) => void; // 変更時に page を 1 にリセット
  reload: () => void;
}

function useEventList(perPage?: number): UseEventListResult;
```

### fetchEvents 拡張（後方互換）

```typescript
export async function fetchEvents(
  page: number = 1,
  perPage: number = 20,
  filters: EventListFilters = {}
): Promise<EventsResponse> {
  const params = new URLSearchParams({
    page: String(page),
    per_page: String(perPage),
  });
  if (filters.protocol) params.set("protocol", filters.protocol);
  if (filters.source_ip) params.set("source_ip", filters.source_ip);
  if (filters.since) params.set("since", filters.since);
  if (filters.until) params.set("until", filters.until);
  // ... GET /api/v1/events?<params>
}
```

- 第3引数 `filters` はデフォルト `{}` なので、既存の `useRecentEvents`（2引数呼び出し）は影響を受けない

### EventDetailModal のインターフェース

```typescript
interface EventDetailModalProps {
  event: AttackEvent | null; // null のとき非表示
  onClose: () => void;
}
```

- `event` が `null` でない間だけモーダルを表示する
- `raw_data` は `JSON.stringify(event.raw_data, null, 2)` で整形し、等幅フォントの `<pre>` に表示する
- Esc キー / 背景クリック / 閉じるボタンで `onClose` を呼ぶ

## Data Models

新しい API・DB モデルは追加しない。既存の型を利用・拡張する。

### AttackEvent 型の扱い

バックエンドの一覧 API は現状 `attack_type` / `severity` をレスポンスに含めていない。表示は既存の項目（時刻・IP・ポート・プロトコル・イベントタイプ）で成立するため、本機能では必須としない。本 spec では表示項目を既存レスポンスの範囲に限定し、型の破壊的変更は行わない。

```typescript
// types/index.ts（EventListFilters を追加）
export interface EventListFilters {
  protocol?: "ssh" | "http";
  source_ip?: string;
  since?: string;
  until?: string;
}
```

### 表示項目（EventTable）

| 列 | ソース | 備考 |
|----|--------|------|
| Time | `timestamp` | ローカル日時表示 |
| Source IP | `source_ip` | 等幅フォント |
| Src Port | `source_port` | |
| Dst Port | `destination_port` | |
| Protocol | `protocol` | ssh/http でバッジ色分け（既存踏襲） |
| Event Type | `event_type` | |
| （操作） | - | 行クリックまたは「詳細」で詳細モーダル |

## View Switching Design

`App.tsx` を以下のように変更する。

```typescript
type View = "dashboard" | "events";

function App() {
  const [authed, setAuthed] = useState(isAuthenticated());
  const [view, setView] = useState<View>("dashboard");

  if (!authed) return <LoginPage onLoginSuccess={() => setAuthed(true)} />;

  const logout = () => setAuthed(false);
  return view === "dashboard"
    ? <DashboardPage onLogout={logout} onNavigate={setView} currentView={view} />
    : <EventListPage onLogout={logout} onNavigate={setView} currentView={view} />;
}
```

- ナビゲーションは共通の `Header`（または各ページ上部のナビ）に「Dashboard」「Events」の切替を置き、`onNavigate` を呼ぶ
- 未認証時は従来通り `LoginPage` のみを表示する（FR-5）

## Pagination Design

- `useEventList` が `page`（1始まり）と `perPage`（既定 50、最大 100）を保持する
- レスポンスの `pagination`（`page` / `per_page` / `total` / `total_pages`）を UI に表示する
- 「前へ」は `page <= 1` で無効化、「次へ」は `page >= total_pages` で無効化する
- フィルタ変更時は `setFilters` 内で `page` を 1 に戻してから再取得する（FR-3）

## Error Handling

| 障害シナリオ | 対処 |
|------------|------|
| 一覧取得の通信エラー | `error` state に格納し、テーブル領域にエラーメッセージを表示（クラッシュしない） |
| 401（認証失敗） | 既存 `fetchWithAuth` が `AuthError` を投げ、認証情報を破棄。呼び出し側でログイン画面へ戻す |
| `raw_data` が空/不整合 | モーダルで「リクエスト内容なし」を表示し、JSON 整形は try/catch でフォールバック |
| フィルタの不正入力（IP 形式など） | サーバー側バリデーションに委譲。エラー時は FR-6 のエラー表示 |

## Testing Strategy

| レイヤー | テスト手法 | ツール |
|---------|-----------|--------|
| fetchEvents（フィルタ付与） | ユニットテスト（URL パラメータ生成） | Vitest（既存にあれば利用、なければ手動確認） |
| useEventList | フックの状態遷移（page リセット等） | Vitest / 手動確認 |
| 型チェック | tsc | `npm run build` の型チェック |
| ビルド | ビルド成功確認 | `npm run build` |

- フロントエンドに既存テスト基盤が無い場合は、最低限 `npm run build`（型チェック含む）で検証する。バックエンドは変更しないため Python 側の再検証は不要。

## Correctness Properties

### Property 1: 全件到達性

一覧はページ送りによって全イベントに到達できる（一括取得はしない）。

**Validates: Requirements 2.1**

### Property 2: フィルタ変更時のページリセット

フィルタ条件が変更されたとき、必ず 1 ページ目から再取得される。

**Validates: Requirements 3.4**

### Property 3: 詳細取得の副作用なし

詳細モーダルは一覧取得時に得た `raw_data` のみを表示し、追加の API 呼び出しを行わない。

**Validates: Requirements 4.1**

### Property 4: 後方互換

既存の `useRecentEvents` / `fetchEvents` の 2 引数呼び出しは挙動が変わらない。

**Validates: Requirements 3.1**

### Property 5: 未認証時の非表示

未認証状態では一覧画面を表示しない。

**Validates: Requirements 5.2**

### Property 6: 障害時の非クラッシュ

データ取得に失敗しても画面はクラッシュせず、エラー表示に留まる。

**Validates: Requirements 6.1**
