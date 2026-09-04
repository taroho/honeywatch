# Implementation Plan: GeoIP によるアクセス元 IP の地理情報表示

## Overview

本実装計画は、design.md に基づき、攻撃イベントの送信元 IP（`source_ip`）を MaxMind GeoLite2 でオンザフライに地理情報へ変換し、Dashboard 上で可視化する機能を段階的に構築する。

実装は既存コード構成に合わせ、次の依存順で進める。

1. 依存ライブラリ追加・設定（`pyproject.toml`, `core/config.py`, `.env`, `.gitignore`）
2. `GeoIP_Resolver`・`GeoLocation` の実装（`analysis/geoip.py`）
3. 国別集計ロジック（`analysis/geoip.py`）
4. Repository への件数集計メソッド追加（`db/repositories/attack.py`）
5. API エンドポイントと依存注入・lifespan（`api/routes/geo.py`, `api/deps.py`, `api/main.py`）
6. フロントエンド（`types/index.ts`, `api/client.ts`, `hooks/`, `components/`）
7. プロパティテスト・ユニットテスト・検証

地理情報は永続化しない方針のため、`attack_events` テーブルのスキーマ変更・マイグレーションタスクは作成しない。テストは pytest + Hypothesis を用い、design の Correctness Properties（Property 1〜9）を検証する。Geo_Map（地図表示）は Dashboard に標準表示する。

## Tasks

- [x] 1. 依存ライブラリと GeoIP 設定のセットアップ
  - [x] 1.1 依存ライブラリを追加し `uv sync` を実行する
    - `pyproject.toml` の本体 `dependencies` に `geoip2==4.8.0`, `maxminddb==2.6.2` を追加する
    - `pyproject.toml` の dev 依存に `hypothesis==6.112.1` を追加する（注: `mmdbencoder` は PyPI に存在しないため追加せず、テスト用 .mmdb は geoip2 リーダーのモックで代替した）
    - `uv sync` を実行してロックファイルを更新する
    - _Requirements: 1.1, 2.1_

  - [x] 1.2 `GeoIPSettings` を追加し `Settings` に統合する
    - `src/honeywatch/core/config.py` に `GeoIPSettings`（`env_prefix="GEOIP_"`, `database_path`, `cache_size`, `enabled`）を追加する
    - `Settings` に `geoip: GeoIPSettings = GeoIPSettings()` を統合する
    - _Requirements: 1.9_

  - [x] 1.3 GeoIP データベースの配置と環境設定を行う
    - `.env`（および `.env.example` が存在すれば同様に）へ `GEOIP_DATABASE_PATH=data/geoip/GeoLite2-City.mmdb`, `GEOIP_CACHE_SIZE=10000`, `GEOIP_ENABLED=true` を追加する
    - `.gitignore` に `data/geoip/` を追加し `.mmdb`・ライセンスキーをコミット対象外にする
    - `data/geoip/` ディレクトリを作成し、取得済みの `GeoLite2-City.mmdb` を配置する運用手順を README もしくは docs に追記する
    - _Requirements: 1.9_

- [x] 2. GeoLocation データモデルと GeoIP_Resolver を実装する
  - [x] 2.1 `GeoLocation` データモデルを実装する
    - `src/honeywatch/analysis/geoip.py` に `@dataclass(frozen=True)` の `GeoLocation`（`country_code`, `country_name`, `region`, `city`, `latitude`, `longitude`）を実装する
    - `unresolved()` クラスメソッドと `is_resolved` プロパティを実装する
    - _Requirements: 2.1, 2.5_

  - [x] 2.2 `GeoIPResolver` のロード処理を実装する
    - `src/honeywatch/analysis/geoip.py` に `GeoIPResolver.__init__` / `load(settings)` / `is_loaded` / `close()` を実装する
    - 正常ロードで読み込み済み状態へ遷移し info ログを1件出力する
    - パス不在で未ロード状態で初期化し error ログを1件出力する
    - ファイル破損・不正形式で未ロード状態で初期化し error ログを1件出力する
    - ログは既存の `core/logging.py`（structlog）を用いる
    - _Requirements: 1.1, 1.2, 1.4, 1.5_

  - [x] 2.3 `GeoIPResolver.resolve` と LRU キャッシュを実装する
    - `src/honeywatch/analysis/geoip.py` に `resolve(ip)` を実装する
    - 未ロード／`enabled=False` は DB 参照せず未解決を返し、未ロード時は warning ログを1件出力する
    - None／空文字／解析不能文字列は未解決を返し、入力値と不正の旨の warning ログを1件出力する
    - プライベート／ループバック／リンクローカル／予約 IP は DB 参照せず未解決を返す（ログ不要）
    - 未登録 IP（`AddressNotFoundError`）は未解決を返す
    - 一部フィールド欠損は当該フィールドを None、取得できたフィールドは値を保持する
    - `cache_size` を上限とするプロセス内 LRU に結果（未解決含む）を格納する
    - _Requirements: 1.3, 1.6, 1.7, 1.8, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x]* 2.4 テスト用 `.mmdb` fixture を `conftest.py` に用意する
    - `tests/test_analysis/` 配下（または `tests/conftest.py`）に既知の少数エントリを持つテスト用 `.mmdb`（`mmdbencoder` で生成）または `geoip2` リーダーをモックした fixture を用意する
    - ロード済み Resolver・未ロード Resolver の fixture を提供する
    - _Requirements: 1.1, 1.3_

  - [x]* 2.5 GeoIP_Resolver のプロパティテストを書く
    - `tests/test_analysis/test_geoip.py` に Hypothesis によるプロパティテストを実装する
    - 各テストに `# Feature: 4-feat-geoip-ip-location, Property N: ...` タグを付す
    - **Property 1: ロード済み Resolver はパブリック IP を値域・形式を満たす Geo_Location に解決する**（Validates: Requirements 1.3, 2.1）
    - **Property 2: 未ロード状態ではすべての IP が未解決になる**（Validates: Requirements 1.6, 2.6）
    - **Property 3: プライベート・予約 IP は DB を参照せず未解決になる**（Validates: Requirements 1.7, 2.3）
    - **Property 4: 不正な IP 文字列は未解決になる**（Validates: Requirements 2.4）

  - [x]* 2.6 GeoIP_Resolver のユニットテストを書く
    - `tests/test_analysis/test_geoip.py` にログ出力・状態遷移・エッジケースの例示テストを実装する
    - ロード成功で info ログ1件・`is_loaded=True`（1.2）、パス不在／破損で未ロード＋error ログ1件（1.4, 1.5）
    - 未ロード時 resolve で warning ログ1件（2.6）、一部フィールド欠損の部分保持（2.5）、未登録パブリック IP で未解決（1.8, 2.2）
    - _Requirements: 1.2, 1.4, 1.5, 1.8, 2.2, 2.5, 2.6_

- [x] 3. 国別集計ロジックを実装する
  - [x] 3.1 `CountryCount` と `CountryAggregator.aggregate` を実装する
    - `src/honeywatch/analysis/geoip.py` に `UNKNOWN_COUNTRY = "UNKNOWN"`、`@dataclass(frozen=True)` の `CountryCount`、`CountryAggregator.aggregate` を実装する
    - 各 IP を resolver で解決し `country_code` 単位で件数を合算する
    - 未解決 IP は `UNKNOWN` 区分に合算する
    - 件数降順・同数は国コード昇順でソートする
    - `max_countries`（既定1000）件に切り詰める
    - _Requirements: 5.1, 5.2, 5.3, 5.9, 6.2_

  - [x]* 3.2 国別集計ロジックのプロパティテストを書く
    - `tests/test_analysis/test_geoip.py` に Hypothesis によるプロパティテストを実装する
    - 各テストに `# Feature: 4-feat-geoip-ip-location, Property N: ...` タグを付す
    - **Property 6: 国別集計は件数を保存し、未解決 IP を「不明」区分に合算する**（Validates: Requirements 5.1, 5.9）
    - **Property 7: 国別集計はソート順と件数上限の不変条件を満たす**（Validates: Requirements 3.4, 5.2, 5.3）

- [x] 4. Repository に IP 別件数集計メソッドを追加する
  - [x] 4.1 `AttackEventRepository.get_ip_counts` を実装する
    - `src/honeywatch/db/repositories/attack.py` に `get_ip_counts(since, until)` を追加する
    - `GROUP BY source_ip` で件数を集計し、期間指定は両端を含む（`>= since`, `<= until`）
    - `since`/`until` がいずれも None の場合は全期間を対象とする
    - 既存メソッドのシグネチャは変更しない（後方互換）
    - _Requirements: 5.5, 5.6, 6.4_

  - [ ]* 4.2 `get_ip_counts` のユニットテストを書く
    - `tests/test_db/`（既存構成に合わせて配置）に期間境界の両端包含（5.6）・全期間集計（5.5）・0 件で空結果（5.8）の例示テストを実装する
    - _Requirements: 5.5, 5.6, 5.8_

- [x] 5. API エンドポイントと依存注入・ライフサイクルを実装する
  - [x] 5.1 GeoIP_Resolver の依存注入と lifespan 構築を実装する
    - `src/honeywatch/api/deps.py` に `get_geoip_resolver(request)` と `GeoIPResolverDep` を追加する
    - `src/honeywatch/api/main.py` の lifespan で `app.state.geoip_resolver = GeoIPResolver.load(settings.geoip)` を構築し、シャットダウン時に `close()` する
    - _Requirements: 1.1_

  - [x] 5.2 `GET /geo/ips/{source_ip}` を実装する
    - `src/honeywatch/api/routes/geo.py` に `APIRouter(prefix="/geo", tags=["geo"])` を新設し、`main.py` にルーターを登録する
    - 既存 `analysis.py` と同じ依存注入（`AuthUser`, `DbSession`）スタイルを用いる
    - 指定 IP の Geo_Location を JSON で返す。不正 IP は `HTTPException(400)` で地理情報を返さない
    - 未解決／Resolver 利用不可は geo 各フィールド null の JSON を返す
    - _Requirements: 3.1, 3.2, 3.5, 3.6_

  - [x] 5.3 `GET /geo/top-ips` を実装する
    - `src/honeywatch/api/routes/geo.py` に Top IP（クエリ `limit` 1〜100 既定10, `period`）に Geo_Location を付与するエンドポイントを実装する
    - 各エントリに `geo` を付与し（未解決は各 null）、件数降順・最大100件で返す
    - _Requirements: 3.3, 3.7_

  - [x] 5.4 `GET /geo/country-summary` を実装する
    - `src/honeywatch/api/routes/geo.py` に国別集計エンドポイント（クエリ `start`, `end` ISO 8601 任意）を実装する
    - `get_ip_counts` と `CountryAggregator.aggregate` を連携させる
    - `start`/`end` 未指定は全期間、両端を含む期間指定、対象0件は `countries: []`
    - `start`/`end` が ISO 8601 でない、または `start > end` は `HTTPException(400)` で既存データ不変
    - _Requirements: 3.4, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9_

  - [x]* 5.5 GeoIP API のプロパティテストを書く
    - `tests/test_api/test_geo.py` に Hypothesis によるプロパティテストを実装し、`GeoIPResolver` をモック注入して DB／`.mmdb` に依存しない形で検証する
    - 各テストに `# Feature: 4-feat-geoip-ip-location, Property N: ...` タグを付す
    - **Property 5: Top IP 応答は各エントリに Geo_Location を持ち、件数降順・最大100件である**（Validates: Requirements 3.3, 3.7）
    - **Property 9: 開始日時が終了日時より後の期間は常にエラーになる**（Validates: Requirements 5.7）

  - [x]* 5.6 GeoIP API のユニットテストを書く
    - `tests/test_api/test_geo.py` に正常系・異常系の例示テストを実装する
    - 正常系（3.1）・未解決応答（3.2）・不正 IP で 400（3.5）・Resolver 利用不可時の null 応答（3.6）・ISO 8601 不正で 400（5.7）・過去データも resolve される（6.3, 6.4）
    - _Requirements: 3.1, 3.2, 3.5, 3.6, 5.7, 6.3, 6.4_

- [x] 6. Checkpoint - バックエンドのテストが通ることを確認する
  - Ensure all tests pass, ask the user if questions arise.
  - `uv run pytest`, `uv run mypy .`, `uv run ruff check .` を実行し、エラーがないことを確認する

- [x] 7. フロントエンドの型・API クライアント・hooks を実装する
  - [x] 7.1 GeoIP 関連の型定義を追加する
    - `frontend/src/types/index.ts` に `GeoLocation`, `GeoTopIPEntry`（`TopIPEntry` 拡張）, `GeoTopIPsResponse`, `CountryCount`, `CountrySummaryResponse` を追加する
    - 既存の `TopIPEntry` / `AttackEvent` は維持する（後方互換）
    - _Requirements: 3.1, 3.3, 5.1_

  - [x] 7.2 API クライアント関数を追加する
    - `frontend/src/api/client.ts` に `fetchIpGeo(sourceIp)`, `fetchGeoTopIPs(limit, period)`, `fetchCountrySummary(start?, end?)` を既存 `fetchWithAuth` パターンで追加する
    - _Requirements: 3.1, 3.3, 3.4_

  - [x] 7.3 hooks を追加する
    - `frontend/src/hooks/useGeoTopIPs.ts`（30秒ポーリング、既存 `useTopIPs` と同型）を追加する
    - `frontend/src/hooks/useCountrySummary.ts`（国別ランキング取得）を追加する
    - _Requirements: 4.1, 4.5_

- [x] 8. フロントエンドの表示コンポーネントを実装する
  - [x] 8.1 `formatCountry` 表示ヘルパーを実装する
    - `frontend/src/` の共通ヘルパー（例 `utils/format.ts` もしくは既存の共通箇所）に `formatCountry(geo)` を実装する
    - `country_code` が null なら固定文言「不明」、それ以外は `国名 (国コード)` 形式で返す
    - _Requirements: 4.3, 4.4_

  - [ ]* 8.2 `formatCountry` のテストを書く
    - vitest 等が導入済みならプロパティ相当のテスト、未導入なら例示テストを実装する
    - **Property 8: 未解決の Geo_Location は「不明」と表示される**（Validates: Requirements 4.3, 4.4）

  - [x] 8.3 既存テーブルに「国」列を追加する
    - `frontend/src/components/TopIPsTable.tsx` と `frontend/src/components/EventTable.tsx` に国コード＋国名を表示する「国」列を追加する
    - `formatCountry` を用い、未解決・プライベートは「不明」を表示し、行の他項目の表示は維持する
    - イベント一覧は 1 ページあたり最大100件に対して表示する
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 8.4 `CountryRankingTable` を新規実装しページに組み込む
    - `frontend/src/components/CountryRankingTable.tsx` を新規作成し、`useCountrySummary` を用いて国別攻撃件数を降順ランキングで上位最大20か国表示する
    - 対象0件時は「集計対象データがありません」相当の表示を行う
    - Dashboard ページ（`frontend/src/pages/DashboardPage.tsx`）に組み込み配線する
    - _Requirements: 4.5, 4.6_

  - [ ]* 8.5 コンポーネントのレンダリングテストを書く
    - vitest 等が導入済みなら `TopIPsTable`/`EventTable` の国列（4.1, 4.2）と `CountryRankingTable` の降順表示・0件表示（4.5, 4.6）の例示レンダリングテストを実装する
    - _Requirements: 4.1, 4.2, 4.5, 4.6_

- [x] 9. Checkpoint - フロントエンドのビルドとバックエンドの検証を確認する
  - Ensure all tests pass, ask the user if questions arise.
  - `cd frontend && npm run build` でフロントエンドがビルドできることを確認する
  - `uv run pytest`, `uv run mypy .`, `uv run ruff check .` を再実行し、全体がグリーンであることを確認する

- [x] 10. Geo_Map（地図表示）
  - [x] 10.1 `GeoMap` コンポーネントを実装する
    - `frontend/src/components/GeoMap.tsx` を新規作成し、緯度経度を持つ攻撃元 IP を地図上のマーカーとして表示する
    - 緯度経度が存在しない IP はマーカーとして表示しない
    - _Requirements: 4.7, 4.8_
  - [x] 10.2 `GeoMap` を Dashboard に組み込む
    - `frontend/src/pages/DashboardPage.tsx` の Detection Analysis セクション直上に `GeoMap` を全幅で常時表示する
    - `useGeoTopIPs` の結果を entries として渡す
    - _Requirements: 4.7, 4.8_

## Notes

- `*` を付したサブタスクはオプション（テスト）で、MVP を優先する場合はスキップできる。トップレベルタスクにはオプション印を付けない。
- Geo_Map（Task 10）は Dashboard の Detection Analysis 直上に常時表示する。
- 各タスクはトレーサビリティのため対応する Requirement を参照する。
- プロパティテストは design.md の Correctness Properties（Property 1〜9）を検証し、各テストに `# Feature: 4-feat-geoip-ip-location, Property N: ...` タグを付す。
- 地理情報は永続化しないため、`attack_events` のスキーマ変更・マイグレーションタスクは含めない。
- Checkpoint では `uv run pytest` / `uv run mypy .` / `uv run ruff check .` と `npm run build` による検証を行う。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1", "2.2", "4.1"] },
    { "id": 2, "tasks": ["2.3", "2.4", "4.2"] },
    { "id": 3, "tasks": ["2.5", "2.6", "3.1", "5.1"] },
    { "id": 4, "tasks": ["3.2", "5.2", "5.3", "5.4"] },
    { "id": 5, "tasks": ["5.5", "5.6", "7.1"] },
    { "id": 6, "tasks": ["7.2", "8.1"] },
    { "id": 7, "tasks": ["7.3", "8.2", "8.3"] },
    { "id": 8, "tasks": ["8.4"] },
    { "id": 9, "tasks": ["8.5", "10.1"] }
  ]
}
```
