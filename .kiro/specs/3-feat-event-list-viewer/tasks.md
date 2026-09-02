# Implementation Plan

## Overview

攻撃イベント一覧機能の実装計画。型定義・API クライアント拡張 → 一覧取得フック → 表示系コンポーネント（詳細モーダル・テーブル・フィルタ・ページネーション）→ 一覧ページ統合 → ナビゲーション・ビュー切替 → ビルド検証の順で進める。バックエンドは変更せず、既存 `GET /api/v1/events` を利用する。既存 Dashboard の動作を壊さないよう後方互換を保つ。

## Tasks

- [x] 1. フロントエンドの型定義を拡張する。`frontend/src/types/index.ts` に `EventListFilters`（protocol / source_ip / since / until、いずれも任意）を追加する。既存の AttackEvent / Pagination / EventsResponse はそのまま利用（破壊的変更なし）。_Requirements: 3.1, 3.2, 3.3_ _Properties: Property 4_
- [x] 2. API クライアントの `fetchEvents` を後方互換で拡張する。`frontend/src/api/client.ts` に第3引数 `filters: EventListFilters = {}` を追加し、値がある場合のみ protocol / source_ip / since / until をクエリに付与する。既存の 2 引数呼び出し（useRecentEvents）の挙動を変えない。_Requirements: 3.1, 3.2, 3.3_ _Properties: Property 3, Property 4_
- [x] 3. `useEventList` フックを実装する。`frontend/src/hooks/useEventList.ts` を新規作成し、page（既定1）/ filters / perPage（既定50）を保持して events / pagination / loading / error を返す。setFilters はフィルタ更新時に page を 1 にリセットして再取得する。setPage / reload を提供。401 は既存 AuthError に委譲、その他は error state に格納する。_Requirements: 2.1, 2.2, 3.4, 3.5, 6.1, 6.2_ _Properties: Property 1, Property 2, Property 6_
- [x] 4. `EventDetailModal` を実装する。`frontend/src/components/EventDetailModal.tsx` を新規作成し、`event: AttackEvent | null` と onClose を受け取る。基本情報と raw_data を JSON 整形（try/catch フォールバック）して pre に表示する。Esc / 背景クリック / 閉じるボタンで閉じる。既存デザイントークンを踏襲する。_Requirements: 4.1, 4.2, 4.3_ _Properties: Property 3_
- [x] 5. `EventTable` を実装する。`frontend/src/components/EventTable.tsx` を新規作成し、events / loading を受け取って Time / Source IP / Src Port / Dst Port / Protocol / Event Type を表示する。行クリックで onSelect を呼ぶ。0 件時は空状態を表示。既存 RecentEventsTable のスタイルを踏襲する。_Requirements: 1.1, 1.2, 1.3, 4.1_ _Properties: Property 6_
- [x] 6. `EventFilters` を実装する。`frontend/src/components/EventFilters.tsx` を新規作成し、protocol（ssh/http/未指定）/ source_ip / 期間（開始・終了）の入力 UI を提供する。適用時に onChange(filters)、クリアで全解除する。_Requirements: 3.1, 3.2, 3.3, 3.5_ _Properties: Property 2_
- [x] 7. `Pagination` を実装する。`frontend/src/components/Pagination.tsx` を新規作成し、pagination と onPageChange を受け取る。現在ページ / 総ページ数 / 総件数を表示し、前へ・次へを端で無効化する。_Requirements: 2.2, 2.3_ _Properties: Property 1_
- [x] 8. `EventListPage` を実装して統合する。`frontend/src/pages/EventListPage.tsx` を新規作成し、useEventList で EventFilters / EventTable / Pagination / EventDetailModal を組み合わせる。選択イベントを state 保持し、モーダルを閉じてもページ・フィルタを維持する。エラー時はエラー領域を表示する。onLogout / onNavigate / currentView を受け取りヘッダーを配置する。_Requirements: 1.1, 2.1, 4.2, 4.3, 5.1, 6.1_ _Properties: Property 6_
- [x] 9. `Header` にビュー切替ナビゲーションを追加する。`frontend/src/components/Header.tsx` を拡張し、Dashboard / Events の切替 UI（onNavigate / currentView）を追加する。両ページで共通利用できるようにする。_Requirements: 5.1_
- [x] 10. `App.tsx` にビュー切替を組み込む。view state（"dashboard" | "events"）を追加し、認証済み時に view に応じて DashboardPage / EventListPage を出し分ける。未認証時は LoginPage のみ表示。DashboardPage に onNavigate / currentView を渡す。_Requirements: 5.1, 5.2_ _Properties: Property 5_
- [ ] 11. ビルド・型チェックで検証する。`cd frontend && npm run build` を実行し、型・ビルドエラーがないことを確認する。エラーは修正する。既存 useRecentEvents / DashboardPage が引き続き動作することを確認する。_Requirements: 1.1, 5.1, 6.1_ _Properties: Property 4_

## Task Dependency Graph

```json
{
  "waves": [
    [1],
    [2],
    [3, 4, 5, 6, 7],
    [8],
    [9],
    [10],
    [11]
  ]
}
```

## Notes

- タスク 1 → 2 → 3 は順序依存（型 → クライアント → フック）
- タスク 4〜7（詳細モーダル / テーブル / フィルタ / ページネーション）は相互に独立で並列実行可能。EventListPage 統合前に揃っていればよい
- タスク 8（EventListPage）はフック（3）と表示系コンポーネント（4〜7）の完了に依存
- タスク 9 → 10 → 11 は順序依存
- バックエンドは変更しないため Python 側の再検証は不要。検証はフロントの `npm run build`（型チェック含む）で行う
