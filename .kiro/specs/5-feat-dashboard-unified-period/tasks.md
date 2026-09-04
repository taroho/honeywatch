# Implementation Plan: Dashboard 統一期間セレクタ

## Overview

本実装計画は spec `5-feat-dashboard-unified-period` の design.md に沿って、Dashboard の期間指定を単一の統一期間セレクタ（`1h`/`6h`/`24h`/`7d`/`1y`/`all`、初期 `24h`）に一本化する。

実装は依存順に進める:

1. バックエンド基盤: 共通ヘルパー `period.py` 新規作成 + リポジトリ集計メソッドの `since` を `datetime | None` 許容化。
2. ルート統一・拡張: `dashboard.py`（summary/timeline）/ `analysis.py` / `geo.py`（top-ips）を `resolve_period_range` と `PERIOD_PATTERN` に統一し、`1y`/`all` に対応。
3. バックエンドテスト: Correctness Properties（Property 1〜4）を Hypothesis で検証 + unit / example + 非回帰。
4. Checkpoint（`uv run pytest` / `uv run mypy .` / `uv run ruff check .`）。
5. フロント: `useDashboardSummary` / `client.ts` → `DashboardPage.tsx` 統一セレクタ・`periodToRange`・カード表題文言。
6. Checkpoint（フロントビルド検証はユーザー環境）。

各タスクは具体的なファイルパスと対応 Requirement / Property を明記する。テスト系サブタスクは `*` を付してオプションとするが、Correctness Properties の検証タスクは必ず含める。

## Tasks

- [x] 1. バックエンド基盤: period 共通ヘルパーとリポジトリの since None 許容化
  - [x] 1.1 共通ヘルパー `period.py` を新規作成
    - `src/honeywatch/api/period.py` を作成する
    - `PERIOD_PATTERN = "^(1h|6h|24h|7d|1y|all)$"` を定義する
    - `_PERIOD_MAP`（`1h`/`6h`/`24h`/`7d`=従来値、`1y`=`timedelta(days=365)`。`all` は含めない）を定義する
    - `resolve_period_range(period: str) -> tuple[datetime | None, datetime]` を実装する（`all`→`(None, now)`、`1y`→`(now - 365d, now)`、他→`(now - timedelta, now)`。`now = datetime.now(UTC)`）
    - Google スタイル docstring と型アノテーションを付与する
    - _Requirements: 3.1, 3.2, 3.3, 9.1_

  - [x] 1.2 リポジトリ集計メソッドの `since` を `datetime | None` 許容化
    - `src/honeywatch/db/repositories/attack.py` を編集する
    - `get_summary` / `get_timeline` / `count_by_attack_type` / `count_by_severity` / `get_ip_aggregates_for_ranking` の `since` を `datetime | None` に緩和し、`since is None` のとき下限フィルタ（`timestamp >= since`）を付けないよう条件分岐する（`until` は必須のまま）
    - `get_top_ips` の `since` も `datetime | None` に緩和する（4.01 と同一パターン）
    - `get_ip_counts` は変更しない（既に None 許容済み）
    - 非 None 呼び出しの挙動が従来と一致すること（後方互換）を保つ
    - _Requirements: 3.2, 5.3, 6.3, 7.5_

- [x] 2. ルートの period 統一・拡張
  - [x] 2.1 `dashboard.py` の summary / timeline を統一・拡張
    - `src/honeywatch/api/routes/dashboard.py` を編集する
    - `summary`: period パラメータを新設（`Query(default="24h", pattern=PERIOD_PATTERN)`）し本日固定を廃止。`resolve_period_range` で `(since, until)` を得て `get_summary(since=since, until=until)` を呼ぶ。レスポンスキー（`attacks_today` 等）は不変。`period_start` は `since is None`（all）のとき `null` を返す
    - `timeline`: pattern を `PERIOD_PATTERN` に統一し `1y`/`all` を受理。`interval`（`5m`/`15m`/`1h`）は維持。`period in ("1y", "all")` のとき `interval_minutes = max(interval_minutes, 60)` にクランプ
    - `/dashboard/top-ips` は `resolve_period_range` への置き換え + pattern 統一のみ行う（挙動不変・`get_top_ips` の since None 許容化に追従）
    - _Requirements: 4.1, 4.2, 4.3, 5.1, 5.2, 5.3, 5.4, 5.5, 9.2_

  - [x] 2.2 `analysis.py` を共通ヘルパーに統一
    - `src/honeywatch/api/routes/analysis.py` を編集する
    - モジュールの `_PERIOD_MAP` / `_period_to_range` を削除する
    - `attack-types` / `severity-summary` / `risk-ranking` の period Query pattern を `PERIOD_PATTERN` に統一し、`resolve_period_range` で `(since, until)` を得て各 repo メソッドへ渡す
    - `risk-ranking` の `limit`（`ge=1, le=100`）と `get_ip_aggregates_for_ranking(limit=max(limit*3, 30))` のロジックは維持する
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 9.2, 9.3_

  - [x] 2.3 `geo.py` の top-ips を共通ヘルパーに統一
    - `src/honeywatch/api/routes/geo.py` を編集する
    - モジュールの `_PERIOD_MAP` を削除する
    - `top-ips` の period Query pattern を `PERIOD_PATTERN` に統一し、`resolve_period_range` で `(since, until)` を得て `get_top_ips(since=since, until=until, limit=limit)` を呼ぶ。以降の geo 付与ロジックは既存のまま
    - `country-summary` は変更しない（start/end 方式を維持）
    - _Requirements: 6.1, 6.2, 6.3, 9.2, 9.3_

- [ ] 3. バックエンドのテスト
  <!-- 3.1〜3.4, 3.6 は実装済み（全 90 テスト green / ruff・mypy clean）。3.5 は実 DB 基盤なし・SQL 検証が脆いため未実施（詳細は 3.5 参照）。オプション群につき親は未完了のまま残す。 -->
  - [x]* 3.1 `resolve_period_range` の property / unit テスト
    - `tests/test_api/test_period.py` を新規作成する
    - **Property 1: period → (since, until) 変換の一貫性**（`all`→`since=None`・`until≈now`、`1y`→差 365日、他→差が `_PERIOD_MAP[period]`）
    - Hypothesis で受理 period を `st.sampled_from([...])` で生成、`@settings(max_examples=100)`
    - タグ: `# Feature: 5-feat-dashboard-unified-period, Property 1: ...`
    - あわせて具体値（`all`/`1y`/`24h`）の example テストを含める
    - **Validates: Requirements 3.1, 3.2, 3.3, 5.2, 5.3, 7.4, 7.5**

  - [x]* 3.2 全ルート共有・不正 period の property テスト
    - `tests/test_api/test_period.py`（3.1 と同一ファイル）に追記する
    - **Property 2: 全 period 対応エンドポイントは同一の period 変換を共有する**（各エンドポイントを TestClient で叩き、モック repo メソッドの `call_args` の `since`/`until` が `resolve_period_range(period)` と整合。対象: summary/timeline/attack-types/severity-summary/risk-ranking/geo top-ips）
    - **Property 3: 不正な period はエラー応答となり集計を返さない**（受理集合を除外した文字列を生成し各ルートが 422、正常レスポンス本体を返さない）
    - 既存モック方針（`app.dependency_overrides` で `verify_credentials`/`get_db` 無効化 + `AttackEventRepository` を `patch`）に合わせる
    - タグ: `# Feature: 5-feat-dashboard-unified-period, Property 2/3: ...`
    - **Validates: Requirements 2.2, 4.2, 5.1, 6.1, 7.1, 7.2, 7.3, 9.1**

  - [x]* 3.3 timeline 粒度クランプの property テスト
    - `tests/test_api/test_dashboard.py`（既存/新規）に追記する
    - **Property 4: 1y / all のタイムラインは時間単位以上の粒度に丸められる**（`period in ("1y","all")` かつ interval を `5m`/`15m`/`1h` から生成し、`get_timeline` の `call_args` の `interval_minutes >= 60`）
    - タグ: `# Feature: 5-feat-dashboard-unified-period, Property 4: ...`
    - **Validates: Requirements 5.5**

  - [x]* 3.4 summary / 各エンドポイントの unit / example テスト
    - `tests/test_api/test_dashboard.py` / `tests/test_api/test_analysis.py` / `tests/test_api/test_geo.py` に追記する
    - summary の period 反映: `?period=1h` と `?period=7d` で `since`/`until` が異なる、未指定で `24h` 相当、`?period=all` で `since=None`・`period_start` が `null`
    - 各エンドポイントの `1y`/`all`: 200 を返し `all` で `since=None` が repo に渡る（summary/timeline/attack-types/severity/risk-ranking/top-ips）
    - 不正 period: `?period=xyz` / `?period=30d` で 422
    - timeline interval 維持: `?period=24h&interval=5m` で `interval_minutes=5`（クランプ対象外）
    - _Requirements: 4.1, 4.2, 4.3, 5.4, 6.2, 7.4, 9.1, 9.2_

  - [ ]* 3.5 リポジトリ `since=None` 許容化の unit テスト
    - `tests/test_collector/` または `tests/test_api/` の既存方針に合わせて追記する
    - `get_summary` / `get_timeline` / `get_top_ips` / `count_by_attack_type` / `count_by_severity` / `get_ip_aggregates_for_ranking` を対象に、`since=None` で下限フィルタなし・非 None で従来どおり両端フィルタとなることを検証する
    - DB 実行が難しい環境では、クエリ構築の分岐（`since is not None` の有無で `where` 句が変わること）を対象とする最小テストに留める（既存モック中心方針）
    - _Requirements: 3.2, 5.3, 6.3, 7.5_
    - **スキップ判断（未実施）**: 実 DB 結合基盤がない（`attack_events` は UUID/JSON 型を用い、インメモリ SQLite が使えない。Task 4.2 でもスキップ実績あり）。`AsyncMock` セッションに対する SQLAlchemy 文の where 句検証は実装詳細に密結合で脆く価値が低い。`since=None`（all）／非 None の分岐挙動は、3.2（Property 2 の全ルート `call_args` 検証）と 3.4（summary/timeline/analysis/geo 各エンドポイントの `since=None` 受け渡し例示）で実質的にカバー済みのため、本サブタスクは未実施とした。

  - [x]* 3.6 非回帰テスト（影響範囲外）
    - 既存テストに影響がないことを確認する
    - `1h`/`6h`/`24h`/`7d` の集計対象期間が不変（後方互換）
    - `/geo/country-summary` / `/geo/ips/{ip}` の既存テストがパス（本 spec 未変更）
    - `/events`（Events 一覧）・Recent Events が period に非依存で従来どおり
    - `login()` の `dashboard/summary`（period なし）呼び出しが引き続き 200/401 判定できる
    - _Requirements: 2.3, 10.1, 10.2, 10.3_

- [x] 4. Checkpoint - バックエンドのテスト・型・リントを確認
  - `uv run pytest` を実行し、追加したテストと既存テストがすべてパスすることを確認する
  - `uv run mypy .` で型エラーがないことを確認する（`since: datetime | None` 化と新規 `period.py` を含む）
  - `uv run ruff check .` を実行する。本 spec で変更したファイル（`period.py` / `attack.py` / `dashboard.py` / `analysis.py` / `geo.py` / 追加テスト）に指摘がないことを確認する
  - 問題があればユーザーに確認する
    - 実施結果: `uv run pytest` 90 passed / `uv run mypy .` no issues (59 files) / `uv run ruff check`（本 spec 変更ファイル）All checks passed。全体 `ruff check .` の既存指摘（migrations 2件・honeypot テスト1件）は本 spec スコープ外のため未対応。

- [x] 5. フロントエンドの統一セレクタ対応
  - [x] 5.1 `useDashboardSummary` と `client.ts` に period を追加
    - `frontend/src/hooks/useDashboardSummary.ts` を編集し、`(period: string = "24h")` 引数を追加、依存配列を `[period]` にし、`fetchDashboardSummary(period)` を呼ぶ
    - `frontend/src/api/client.ts` の `fetchDashboardSummary` に `period: string = "24h"` を追加し、`?period=` を付与して呼ぶ
    - 他の fetch / hook は変更不要（既に period または start/end を受ける）
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 5.2 `DashboardPage.tsx` を統一セレクタに一本化
    - `frontend/src/pages/DashboardPage.tsx` を編集する
    - `UNIFIED_PERIOD_OPTIONS = ["1h","6h","24h","7d","1y","all"] as const` を定義し、単一の `period` state（初期 `"24h"`）にする（既存の `PERIOD_OPTIONS` 4 択・初期 `7d` は廃止）
    - ページ上部（サマリーカード直上）に統一セレクタ UI を配置する（選択中 `bg-hw-accent`、未選択 `bg-hw-card` の既存タブ方式）。Detection Analysis 専用の期間セレクタは削除する
    - 各 hook に `period` を連動: `useDashboardSummary(period)` / `useTimeline(period)` / `useGeoTopIPs(20, period)`（地図 + Top IP テーブル共用）/ `useAttackTypes(period)` / `useSeveritySummary(period)` / `useRiskRanking(10, period)`
    - `periodToRange(period)`（`all`→`{}`、他→`start`/`end` を `resolve_period_range` と同一定義で算出）を追加し、`useCountrySummary(start, end)` に渡す
    - `useRecentEvents(10)`（Recent Events）は非連動のまま据え置く
    - サマリーカードの表題を「本日」等の期間依存文言から期間非依存の文言に変更する
    - `GeoMap.tsx` / `TopIPsTable.tsx` / `CountryRankingTable.tsx` は変更しない
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 4.4, 6.4, 6.6, 8.1, 8.2, 8.3_

- [ ] 6. Checkpoint - フロントビルド検証（ユーザー環境）
  - フロントのビルド検証（`cd frontend && npm run build`）は本環境で npm が使えないため実行できない。ユーザー環境で `npm run build` と目視確認を実施してもらう
  - 目視確認項目: 初期表示で `24h` 選択（1.3）、6 択表示（1.2）、選択中タブの区別（1.4/1.5）、期間切替で Linked_Items 全更新（2.1）、Recent Events / Events 一覧が非連動（2.3）、地図・Top IP テーブルが limit=20 で選択期間連動（6.4/6.6）、国別が選択期間連動・`all` で全期間（8.1〜8.3）、カード表題が期間非依存（4.4）
  - 問題があればユーザーに確認する

## Notes

- タスクに付した `*` はオプション（テスト系サブタスク）で、MVP を急ぐ場合はスキップ可能。ただし Correctness Properties（Property 1〜4）の検証は品質担保のため実施を推奨する。
- 各タスクは design.md の Requirements Traceability と Correctness Properties に対応づけている。
- Checkpoint（タスク 4）の `uv run ruff check .` では、本 spec で変更したファイルのみを確認対象とする。`migrations/` や honeypot テスト等、本 spec と無関係な既存の ruff 既存指摘には触れない。
- フロントのビルド検証（`npm run build`）はこの環境で実行できないため、ユーザー環境に委ねる（タスク 6）。
- 同一ファイルを編集するタスクは Task Dependency Graph で別 wave に分離している（例: `dashboard.py` を書く 2.1 と、そのテストを書く 3.3/3.4）。
- Git 操作・ファイル削除は行わない。本 spec の実装対象外のコード・他 spec は変更しない。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1", "2.2", "2.3"] },
    { "id": 2, "tasks": ["3.1", "3.2", "3.3", "3.4", "3.5", "3.6"] },
    { "id": 3, "tasks": ["5.1"] },
    { "id": 4, "tasks": ["5.2"] }
  ]
}
```
