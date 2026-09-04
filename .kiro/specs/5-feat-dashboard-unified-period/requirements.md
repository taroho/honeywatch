# Requirements Document

## Introduction

本 spec は、HoneyWatch の Dashboard における期間指定を統一することを目的とする。現状、Dashboard の各項目（サマリーカード、タイムライン、Top IP テーブル、攻撃元マップ、攻撃タイプ別、Severity 別内訳、Risk ランキング、国別ランキング）は、項目ごとに期間指定がバラバラである（サマリーカードは本日固定、Detection Analysis セクションは独立の期間セレクタ、国別ランキングは全期間固定など）。

本 spec では、Dashboard 上部に 1 つの統一期間セレクタ（Unified_Period_Selector）を配置し、Recent Events と Events 一覧を除く全項目がその 1 つのセレクタに連動して集計・表示更新されるようにする。期間の選択肢は `1h` / `6h` / `24h` / `7d` / `1y`（直近365日）/ `all`（全期間＝下限なし）の 6 種とする。

親フェーズ `4-feat-geoip-ip-location` および修正 spec `4.01-fix-geoip-map-period-filter` で実装済みの地理情報・期間タブの挙動と整合させる。地理情報は非永続（都度解決）のまま維持し、DB スキーマ変更は行わない。

スコープは Dashboard の期間統一に限定する。新規の可視化項目追加や AI 機能などは本 spec に含めない。

## Glossary

- **Dashboard**: HoneyWatch の攻撃監視ダッシュボード画面。フロントエンドの `DashboardPage` に相当する。
- **Unified_Period_Selector**: Dashboard 上部に配置する単一の期間セレクタ。選択肢は `1h` / `6h` / `24h` / `7d` / `1y` / `all` の 6 種。UI は既存の Detection Analysis 期間セレクタと同一のタブ切り替え方式（選択中タブを視覚的に区別）とする。
- **Period_Option**: Unified_Period_Selector が受け付ける期間選択肢の値。`1h`（直近1時間）/ `6h`（直近6時間）/ `24h`（直近24時間）/ `7d`（直近7日）/ `1y`（直近365日）/ `all`（全期間＝集計下限なし）。
- **Linked_Items**: Unified_Period_Selector に連動して集計・表示更新される Dashboard 項目の集合。サマリーカード（Summary_Cards）、タイムライン（Timeline）、Top IP テーブル（Top_IPs_Table）、攻撃元マップ（Geo_Map）、攻撃タイプ別（Attack_Types）、Severity 別内訳（Severity_Summary）、Risk ランキング（Risk_Ranking）、国別ランキング（Country_Summary）を含む。
- **Excluded_Items**: Unified_Period_Selector に連動しない項目の集合。Recent Events（最新 10 件のイベント表示）と Events 一覧ページを含む。
- **Summary_Cards**: Dashboard 上部のサマリーカード群（攻撃数・ユニーク IP 数・SSH 試行数・HTTP 攻撃数）。`GET /api/v1/dashboard/summary` から取得する。
- **Timeline**: 時間帯別の攻撃数グラフ。`GET /api/v1/dashboard/timeline` から取得する。
- **Top_IPs_Table**: 攻撃数の多い送信元 IP ランキングテーブル。`GET /api/v1/geo/top-ips` から取得する。
- **Geo_Map**: 攻撃元を地図上に表示するマップ。`GET /api/v1/geo/top-ips` から取得する。緯度経度を持つ IP のみマーカー表示する。
- **Attack_Types**: 攻撃タイプ別の集計グラフ。`GET /api/v1/analysis/attack-types` から取得する。
- **Severity_Summary**: Severity 別のイベント件数内訳。`GET /api/v1/analysis/severity-summary` から取得する。
- **Risk_Ranking**: Risk Score の高い IP ランキング。`GET /api/v1/analysis/risk-ranking` から取得する。
- **Country_Summary**: 国別攻撃件数ランキング。`GET /api/v1/geo/country-summary` から取得する。現状 `start` / `end`（ISO 8601）で期間を指定する方式。
- **Summary_Endpoint**: `GET /api/v1/dashboard/summary`。現状 period パラメータを持たず、本日（当日 0 時〜現在）固定で集計する。
- **Timeline_Endpoint**: `GET /api/v1/dashboard/timeline`。現状 period（`1h`/`6h`/`24h`/`7d`）と interval（`5m`/`15m`/`1h`）を受け付ける。
- **Top_IPs_Endpoint**: `GET /api/v1/geo/top-ips`。現状 limit と period（`1h`/`6h`/`24h`/`7d`）を受け付ける。`4.01-fix-geoip-map-period-filter` で `1y` / `all` 追加が設計済み。
- **Attack_Types_Endpoint**: `GET /api/v1/analysis/attack-types`。現状 period（`1h`/`6h`/`24h`/`7d`）を受け付ける。
- **Severity_Endpoint**: `GET /api/v1/analysis/severity-summary`。現状 period（`1h`/`6h`/`24h`/`7d`）を受け付ける。
- **Risk_Ranking_Endpoint**: `GET /api/v1/analysis/risk-ranking`。現状 limit と period（`1h`/`6h`/`24h`/`7d`）を受け付ける。
- **Country_Summary_Endpoint**: `GET /api/v1/geo/country-summary`。現状 start / end（ISO 8601）を受け付け、全期間対応済み。
- **1y**: Period_Option の 1 つ。要求受信時刻から遡って直近 365 日を集計対象とする（集計下限 = now − 365 日）。
- **all**: Period_Option の 1 つ。集計下限を設けず、要求受信時刻以前の全 Attack_Event を集計対象とする。
- **Attack_Event**: Honeypot が観測し記録した攻撃イベント。`attack_events` テーブルに永続化される。

## Requirements

### Requirement 1: 統一期間セレクタの配置

**User Story:** As a セキュリティエンジニア, I want Dashboard 上部に 1 つの期間セレクタがある, so that 全体を 1 か所の操作で同じ期間に揃えて分析できる

#### Acceptance Criteria

1. THE Dashboard SHALL Dashboard 上部に Unified_Period_Selector を 1 つ表示する。
2. THE Unified_Period_Selector SHALL Period_Option として `1h` / `6h` / `24h` / `7d` / `1y` / `all` の 6 種を選択肢として表示する。
3. WHEN Dashboard が初期表示される, THE Unified_Period_Selector SHALL 既定の Period_Option として `24h` を選択状態にする。
4. THE Unified_Period_Selector SHALL 現在選択中の Period_Option を、未選択の Period_Option と視覚的に区別して表示する。
5. THE Unified_Period_Selector SHALL 既存の Detection Analysis 期間セレクタと同一のタブ切り替え方式で表示する。

### Requirement 2: 統一期間セレクタへの連動

**User Story:** As a セキュリティエンジニア, I want 期間を切り替えると対象の全項目が同じ期間で更新される, so that 期間ごとの攻撃傾向を一貫した基準で比較できる

#### Acceptance Criteria

1. WHEN 利用者が Unified_Period_Selector で Period_Option を選択する, THE Dashboard SHALL Linked_Items のすべて（Summary_Cards / Timeline / Top_IPs_Table / Geo_Map / Attack_Types / Severity_Summary / Risk_Ranking / Country_Summary）を、選択された Period_Option の期間で集計した内容に更新する。
2. THE Dashboard SHALL Linked_Items のすべてを、常に Unified_Period_Selector で選択中の同一 Period_Option で集計する。
3. THE Dashboard SHALL Excluded_Items（Recent Events および Events 一覧ページ）を Unified_Period_Selector に連動させない。

### Requirement 3: 期間の意味の定義

**User Story:** As a セキュリティエンジニア, I want 各期間の集計範囲が明確に定義されている, so that 表示された数値がどの範囲を集計したものか正しく解釈できる

#### Acceptance Criteria

1. WHEN Period_Option が `1y` である, THE Dashboard SHALL 要求受信時刻から遡って直近 365 日を集計対象とする。
2. WHEN Period_Option が `all` である, THE Dashboard SHALL 集計下限を設けず要求受信時刻以前の全 Attack_Event を集計対象とする。
3. WHEN Period_Option が `1h` / `6h` / `24h` / `7d` のいずれかである, THE Dashboard SHALL 従来と同一の集計対象期間（要求受信時刻から遡る当該期間）を用いる。

### Requirement 4: サマリーカードの統一期間対応

**User Story:** As a セキュリティエンジニア, I want サマリーカードも選択期間で集計される, so that 本日固定ではなく任意の期間で攻撃状況の概要を把握できる

#### Acceptance Criteria

1. THE Summary_Endpoint SHALL Period_Option（`1h`/`6h`/`24h`/`7d`/`1y`/`all`）を受け付ける period パラメータを提供する。
2. WHEN Summary_Endpoint が period を指定して呼び出される, THE Summary_Endpoint SHALL 指定された Period_Option の集計対象期間で攻撃数・ユニーク IP 数・SSH 試行数・HTTP 攻撃数を集計して返す。
3. WHEN Summary_Endpoint が period を指定せずに呼び出される, THE Summary_Endpoint SHALL 既定の Period_Option として `24h` を用いて集計する。
4. THE Summary_Cards SHALL カードの表題を、特定の期間（例: 本日）に依存しない表記で表示する。

### Requirement 5: タイムラインの1y/all対応

**User Story:** As a セキュリティエンジニア, I want タイムラインで長期間（1y/all）も選べる, so that 長期的な攻撃傾向の推移を確認できる

#### Acceptance Criteria

1. THE Timeline_Endpoint SHALL period パラメータとして `1y` と `all` を追加で受け付ける。
2. WHEN Timeline_Endpoint が period=`1y` で呼び出される, THE Timeline_Endpoint SHALL 直近 365 日を集計対象としたタイムラインデータを返す。
3. WHEN Timeline_Endpoint が period=`all` で呼び出される, THE Timeline_Endpoint SHALL 集計下限を設けず全期間を集計対象としたタイムラインデータを返す。
4. THE Timeline_Endpoint SHALL interval パラメータとして従来の `5m` / `15m` / `1h` を引き続き受け付ける。
5. WHERE Period_Option が `1y` または `all` である, THE Timeline SHALL 集計区間の粒度を時間単位（1 時間以上）とし、区間数が過大にならないようにする。

### Requirement 6: Top IP テーブルおよび攻撃元マップの統一期間対応

**User Story:** As a セキュリティエンジニア, I want Top IP と攻撃元マップも統一期間に連動する, so that 選択した期間の攻撃元 IP と地理的分布を確認できる

#### Acceptance Criteria

1. THE Top_IPs_Endpoint SHALL period パラメータとして `1y` と `all` を追加で受け付ける。
2. WHEN Top_IPs_Endpoint が period=`1y` で呼び出される, THE Top_IPs_Endpoint SHALL 直近 365 日を集計対象とした Top IP ランキングを返す。
3. WHEN Top_IPs_Endpoint が period=`all` で呼び出される, THE Top_IPs_Endpoint SHALL 集計下限を設けず全期間を集計対象とした Top IP ランキングを返す。
4. WHEN Geo_Map が表示のためのデータを要求する, THE Dashboard SHALL Top_IPs_Endpoint に対し limit=20 を指定する。
5. THE Geo_Map SHALL 緯度経度を持つ IP のみをマーカーとして表示する。
6. THE Top_IPs_Table SHALL Unified_Period_Selector で選択中の Period_Option の期間で集計した Top IP ランキングを表示する。

### Requirement 7: 攻撃タイプ別・Severity・Risk ランキングの1y/all対応

**User Story:** As a セキュリティエンジニア, I want 攻撃タイプ別・Severity・Risk ランキングも長期間を選べる, so that 選択した期間の攻撃分類・深刻度・リスク傾向を確認できる

#### Acceptance Criteria

1. THE Attack_Types_Endpoint SHALL period パラメータとして `1y` と `all` を追加で受け付ける。
2. THE Severity_Endpoint SHALL period パラメータとして `1y` と `all` を追加で受け付ける。
3. THE Risk_Ranking_Endpoint SHALL period パラメータとして `1y` と `all` を追加で受け付ける。
4. WHEN Attack_Types_Endpoint / Severity_Endpoint / Risk_Ranking_Endpoint が period=`1y` で呼び出される, THE 当該エンドポイント SHALL 直近 365 日を集計対象とした結果を返す。
5. WHEN Attack_Types_Endpoint / Severity_Endpoint / Risk_Ranking_Endpoint が period=`all` で呼び出される, THE 当該エンドポイント SHALL 集計下限を設けず全期間を集計対象とした結果を返す。

### Requirement 8: 国別ランキングの統一期間対応

**User Story:** As a セキュリティエンジニア, I want 国別ランキングも統一期間に連動する, so that 選択した期間の攻撃元国の分布を確認できる

#### Acceptance Criteria

1. THE Country_Summary SHALL Unified_Period_Selector で選択中の Period_Option の期間で集計した国別攻撃件数ランキングを表示する。
2. WHEN Period_Option が `all` である, THE Country_Summary SHALL 集計下限を設けず全期間を集計対象とする。
3. WHEN Period_Option が `1h` / `6h` / `24h` / `7d` / `1y` のいずれかである, THE Country_Summary SHALL 当該 Period_Option の集計対象期間に一致する期間で集計する。

### Requirement 9: 不正な期間の扱いと後方互換

**User Story:** As a 開発者, I want 不正な period はエラーで拒否され、既存 API の既定挙動が保たれる, so that 誤った入力を早期に検出でき、既存クライアントを壊さずに拡張できる

#### Acceptance Criteria

1. IF period パラメータが `1h` / `6h` / `24h` / `7d` / `1y` / `all` のいずれにも一致しない, THEN THE 当該エンドポイント（Summary_Endpoint / Timeline_Endpoint / Attack_Types_Endpoint / Severity_Endpoint / Risk_Ranking_Endpoint / Top_IPs_Endpoint）SHALL period が不正である旨を示すエラー応答を返し、集計結果を返さない。
2. WHEN period を持つエンドポイントが period を指定せずに呼び出される, THE 当該エンドポイント SHALL 既定の Period_Option として `24h` を用いて集計する。
3. THE limit パラメータを持つエンドポイント（Top_IPs_Endpoint / Risk_Ranking_Endpoint）SHALL limit の既定値と受理範囲（1〜100）を従来どおり維持する。

### Requirement 10: 非機能・スコープ制約

**User Story:** As a 開発者, I want 変更範囲を Dashboard の期間統一に限定する, so that 既存機能への副作用を避け、最小差分で安全に拡張できる

#### Acceptance Criteria

1. THE Dashboard SHALL Excluded_Items（Recent Events および Events 一覧ページ）の集計期間・表示挙動を従来どおり維持する。
2. THE 地理情報 SHALL 永続化せず、リクエストのたびに都度解決する方式を維持する。
3. THE Attack_Event の永続データモデル（`attack_events` テーブル）SHALL 本 spec の変更対象としない。
