# Implementation Plan: Timeline 1y/all の月単位集計

## Overview

本実装計画は spec `5.01-fix-timeline-monthly-bucket` の design.md に沿って、Period_Option が `1y` / `all` のとき Attack Timeline を月単位（Monthly_Bucket）で集計・表示するよう修正する。

実装は依存順に進める:

1. バックエンド基盤: `attack.py` に番兵値 `_MONTH_SENTINEL` と月粒度分岐を追加。
2. ルート: `dashboard.py` の timeline を `1y`/`all` のとき月粒度指定に変更（1h クランプを置換）。
3. バックエンドテスト: Correctness Properties（Property 1〜3）を Hypothesis で検証 + unit / example + 非回帰。
4. Checkpoint（`uv run pytest` / `uv run mypy .` / `uv run ruff check`）。
5. フロント: `AttackTimeline.tsx` に `period` prop 追加・月ラベル整形、`DashboardPage.tsx` で `period` を渡す。
6. Checkpoint（フロントビルド検証はユーザー環境）。

各タスクは具体的なファイルパスと対応 Requirement / Property を明記する。テスト系サブタスクは `*` を付してオプションとするが、Correctness Properties の検証は品質担保のため実施を推奨する。

## Tasks

- [x] 1. バックエンド基盤: 月粒度の番兵値と get_timeline の分岐追加
  - [x] 1.1 `attack.py` に月粒度分岐を追加
    - `src/honeywatch/db/repositories/attack.py` を編集する
    - モジュールレベル定数 `_MONTH_SENTINEL = 43200`（30日相当 = 30*24*60）を定義し、用途をコメントで明記する
    - `get_timeline` の粒度選択の**最上位**に `if interval_minutes >= _MONTH_SENTINEL: trunc_expr = func.date_trunc("month", ...)` を追加する
    - 既存の `<= 5`（minute）/ `<= 15`（quarter_hour）/ `else`（hour）分岐は変更しない
    - `filters` 構築・`select`・`group_by`・`order_by`・整形ロジックは変更しない（レスポンス構造不変）
    - _Requirements: 1.1, 1.2, 1.4, 5.3, 5.4_

- [x] 2. ルート: timeline の 1y/all を月粒度指定に変更
  - [x] 2.1 `dashboard.py` の timeline を月粒度指定に変更
    - `src/honeywatch/api/routes/dashboard.py` を編集する
    - `attack.py` から `_MONTH_SENTINEL` を import する（定数の一元管理）
    - `period in ("1y", "all")` のときの `interval_minutes = max(interval_minutes, 60)`（1h クランプ）を `interval_minutes = _MONTH_SENTINEL` に置き換える
    - `1h`/`6h`/`24h`/`7d` は従来どおり `interval_map[interval]` を反映する（変更しない）
    - period / interval の Query pattern は変更しない
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2_

- [ ] 3. バックエンドのテスト
  <!-- 3.1/3.2/3.4/3.5 は実装済み（test_dashboard.py 全 15 テスト green）。3.3（get_timeline 粒度選択の単調性）は
       実 DB 基盤がなく、AsyncMock への SQL 文検証が脆いため未実施。粒度分岐は 3.1/3.2 の call_args 検証で実質カバー。 -->
  - [x]* 3.1 粒度選択の property テスト（1y/all は月粒度）
    - `tests/test_api/test_dashboard.py` に追記する
    - **Property 1: 1y / all は月粒度（番兵値）で集計される**（period を `st.sampled_from(["1y","all"])`、interval を `st.sampled_from(["5m","15m","1h"])` で生成し、TestClient で timeline を叩き、モック `get_timeline` の `call_args.kwargs["interval_minutes"] >= _MONTH_SENTINEL` を検証）
    - `@settings(max_examples=100)`
    - タグ: `# Feature: 5.01-fix-timeline-monthly-bucket, Property 1: ...`
    - 既存モック方針（`app.dependency_overrides` で `verify_credentials`/`get_db` 無効化 + `AttackEventRepository` を `patch`）に合わせる
    - **Validates: Requirements 1.1, 1.2, 1.3**

  - [x]* 3.2 粒度選択の property テスト（短期は interval 反映・後方互換）
    - `tests/test_api/test_dashboard.py` に追記する
    - **Property 2: 1h/6h/24h/7d は interval に応じた粒度で集計される**（period を `st.sampled_from(["1h","6h","24h","7d"])`、interval を生成し、`interval_minutes == {"5m":5,"15m":15,"1h":60}[interval]` かつ `< _MONTH_SENTINEL` を検証）
    - タグ: `# Feature: 5.01-fix-timeline-monthly-bucket, Property 2: ...`
    - **Validates: Requirements 2.1, 2.2, 5.4**

  - [ ]* 3.3 get_timeline 粒度選択の単調性テスト（任意）
    - `tests/test_collector/` または `tests/test_api/` の既存方針に合わせて追記する
    - **Property 3: get_timeline の粒度選択の単調性**（`interval_minutes` を生成し、`>= _MONTH_SENTINEL`→month、`<= 5`→minute、`<= 15`→quarter_hour、それ以外→hour が選択される。DB 実行が難しい環境では、trunc 単位を決めるロジックを関数抽出するか、生成 SQL 文字列の `date_trunc('...')` を検証する最小テストに留める）
    - タグ: `# Feature: 5.01-fix-timeline-monthly-bucket, Property 3: ...`
    - **Validates: Requirements 1.1, 1.2, 2.1, 5.4**

  - [x]* 3.4 unit / example テスト
    - `tests/test_api/test_dashboard.py` に追記する
    - `?period=1y`（interval 既定）で `interval_minutes == _MONTH_SENTINEL`
    - `?period=all&interval=5m` でも `interval_minutes == _MONTH_SENTINEL`（interval 非依存、Requirement 1.3）
    - `?period=24h&interval=5m` で `interval_minutes == 5`（従来維持、Requirement 2.2）
    - `?period=7d`（interval 既定 1h）で `interval_minutes == 60`
    - _Requirements: 1.3, 2.2_

  - [x]* 3.5 非回帰テスト（影響範囲外）
    - 親 spec `5-feat-dashboard-unified-period` の timeline テストが引き続きパスすることを確認する
    - 従来「1h クランプ」を前提に `interval_minutes >= 60` を期待するアサーションは月粒度（`>= _MONTH_SENTINEL >= 60`）でも成立する。`interval_minutes == 60` を厳密に期待する `1y`/`all` 向けアサーションがあれば `_MONTH_SENTINEL` に更新する
    - Summary / Top_IPs / Attack_Types / Severity / Risk_Ranking / Country_Summary の既存テストが不変であること（Requirement 5.1）
    - _Requirements: 5.1, 5.3, 5.4_

- [x] 4. Checkpoint - バックエンドのテスト・型・リントを確認
  - `uv run pytest` を実行し、追加したテストと既存テストがすべてパスすることを確認する
  - `uv run mypy .` で型エラーがないことを確認する（`_MONTH_SENTINEL` の import を含む）
  - `uv run ruff check` を実行し、本 spec で変更したファイル（`attack.py` / `dashboard.py` / 追加テスト）に指摘がないことを確認する
  - 問題があればユーザーに確認する
    - 実施結果: `uv run pytest` 95 passed / `uv run mypy .` no issues (59 files) / `uv run ruff check`（本 spec 変更ファイル）All checks passed。

- [x] 5. フロントエンドの月ラベル対応
  - [x] 5.1 `AttackTimeline.tsx` に period prop と月ラベル整形を追加
    - `frontend/src/components/AttackTimeline.tsx` を編集する
    - `AttackTimelineProps` に `period: string` を追加する
    - `isMonthly = period === "1y" || period === "all"` を判定し、`isMonthly` のとき横軸ラベルを `YYYY/MM`（`getFullYear()` / `getMonth()+1` を 2 桁ゼロ埋め）で整形する
    - `isMonthly` 以外は従来どおり `toLocaleTimeString("ja-JP", { hour, minute })` を用いる
    - Line（Total/SSH/HTTP）・Legend・Tooltip・`dataKey="time"` は変更しない
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 5.2 `DashboardPage.tsx` で period を AttackTimeline に渡す
    - `frontend/src/pages/DashboardPage.tsx` を編集する
    - `<AttackTimeline ... />` に `period={period}` を追加する
    - `useTimeline` / `client.ts` は変更しない
    - _Requirements: 4.1, 4.2_

- [ ] 6. Checkpoint - フロントビルド検証（ユーザー環境）
  - フロントのビルド検証（`cd frontend && npm run build`）は本環境で npm が使えないため実行できない。ユーザー環境で `npm run build` と目視確認を実施してもらう
  - 目視確認項目: `1y`/`all` 選択時に横軸が `YYYY/MM` 表記（4.1）、`1h`〜`7d` は従来の時刻表示（4.2）、Total/SSH/HTTP の線・凡例・Tooltip が従来どおり（4.3）、点数が月数分に減っている（`1y` で最大 13 点程度）
  - 問題があればユーザーに確認する

## Notes

- タスクに付した `*` はオプション（テスト系サブタスク）で、MVP を急ぐ場合はスキップ可能。ただし Correctness Properties（Property 1〜3）の検証は品質担保のため実施を推奨する。
- 各タスクは design.md の Requirements Traceability と Correctness Properties に対応づけている。
- Checkpoint（タスク 4）の `uv run ruff check` では、本 spec で変更したファイルのみを確認対象とする。`migrations/` 等の本 spec と無関係な既存の ruff 指摘には触れない。
- フロントのビルド検証（`npm run build`）はこの環境で実行できないため、ユーザー環境に委ねる（タスク 6）。
- 同一ファイルを編集するタスクは Task Dependency Graph で別 wave に分離している。
- Git 操作・ファイル削除は行わない。本 spec の実装対象外のコード・他 spec は変更しない。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["3.1", "3.2", "3.3", "3.4", "3.5"] },
    { "id": 3, "tasks": ["5.1"] },
    { "id": 4, "tasks": ["5.2"] }
  ]
}
```
