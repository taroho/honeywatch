# Requirements Document

## Introduction

本 spec は、親フェーズ `5-feat-dashboard-unified-period` で実装した Attack Timeline（時間帯別の攻撃数グラフ）の集計粒度・横軸表示を修正するものである。

現状、Timeline_Endpoint は `1y`（直近365日）と `all`（全期間）が選択された場合でも集計粒度を「1 時間」にクランプするに留まる。このため長期間では区間数が過大（`1y` で最大 365×24=8760 点）になり、横軸ラベルも時刻表示のままで、長期的な攻撃傾向を月単位で俯瞰しづらい。

本 spec では、Period_Option が `1y` または `all` のとき、Timeline の集計粒度を **月単位** に変更する。あわせてフロントの横軸ラベルを、月単位のときは年月（`YYYY/MM`）表記で表示する。`1h` / `6h` / `24h` / `7d` の集計粒度・横軸表示は従来どおり変更しない。

スコープは Timeline の `1y` / `all` 時の集計粒度と横軸表示の修正に限定する。他の Dashboard 項目（Summary_Cards / Top_IPs / Attack_Types など）や集計期間そのものの定義（`resolve_period_range`）は変更しない。DB スキーマ変更も行わない。

## Glossary

- **Timeline**: 時間帯別の攻撃数グラフ。フロントエンドの `AttackTimeline` コンポーネントに相当する。`GET /api/v1/dashboard/timeline` からデータを取得する。
- **Timeline_Endpoint**: `GET /api/v1/dashboard/timeline`。period（`1h`/`6h`/`24h`/`7d`/`1y`/`all`）と interval（`5m`/`15m`/`1h`）を受け付ける。
- **Period_Option**: 集計期間の選択肢。`1h` / `6h` / `24h` / `7d` / `1y`（直近365日）/ `all`（全期間＝集計下限なし）。
- **Bucket_Granularity**: Timeline の集計区間の粒度。現状は分（`minute`）・15分（`quarter_hour`）・時間（`hour`）のいずれか。本 spec で「月（`month`）」を追加する。
- **Monthly_Bucket**: 暦月単位の集計区間。各バケットはその月に属する Attack_Event を集計し、バケットの代表時刻はその月の初日 00:00（`date_trunc('month', ...)` に相当）とする。
- **get_timeline**: `AttackEventRepository` のメソッド。`since` / `until` / `interval_minutes` を受け取り、`date_trunc` でバケット集計した結果リストを返す。
- **Attack_Event**: Honeypot が観測し記録した攻撃イベント。`attack_events` テーブルに永続化される。

## Requirements

### Requirement 1: 1y / all の月単位集計

**User Story:** As a セキュリティエンジニア, I want 1y / all の Timeline が月単位で集計される, so that 長期的な攻撃傾向を月ごとの推移として俯瞰できる

#### Acceptance Criteria

1. WHEN Timeline_Endpoint が period=`1y` で呼び出される, THE Timeline_Endpoint SHALL 集計粒度を Monthly_Bucket（暦月単位）として集計した結果を返す。
2. WHEN Timeline_Endpoint が period=`all` で呼び出される, THE Timeline_Endpoint SHALL 集計粒度を Monthly_Bucket（暦月単位）として集計した結果を返す。
3. WHEN Timeline_Endpoint が period=`1y` または `all` で呼び出される, THE Timeline_Endpoint SHALL interval パラメータ（`5m`/`15m`/`1h`）の指定値によらず Monthly_Bucket を用いる。
4. THE Monthly_Bucket SHALL 各バケットの代表時刻をその月の初日 00:00（`date_trunc('month', ...)`）として返す。

### Requirement 2: 1h/6h/24h/7d の従来維持

**User Story:** As a セキュリティエンジニア, I want 短期間（1h〜7d）の Timeline は従来どおり表示される, so that 既存の短期分析の挙動が変わらない

#### Acceptance Criteria

1. WHEN Timeline_Endpoint が period=`1h` / `6h` / `24h` / `7d` のいずれかで呼び出される, THE Timeline_Endpoint SHALL 従来と同一の Bucket_Granularity（interval に応じた分 / 15分 / 時間）で集計する。
2. THE Timeline_Endpoint SHALL period=`1h` / `6h` / `24h` / `7d` において interval パラメータ（`5m`/`15m`/`1h`）を従来どおり反映する。

### Requirement 3: 集計範囲の不変

**User Story:** As a セキュリティエンジニア, I want 月単位化しても各期間の集計対象範囲は変わらない, so that 表示された数値がどの範囲を集計したものか従来と同じ基準で解釈できる

#### Acceptance Criteria

1. THE Timeline_Endpoint SHALL period=`1y` の集計対象を要求受信時刻から遡って直近 365 日とする（範囲の定義は変更しない）。
2. THE Timeline_Endpoint SHALL period=`all` の集計対象を集計下限なし（要求受信時刻以前の全 Attack_Event）とする（範囲の定義は変更しない）。
3. THE 修正 SHALL `resolve_period_range` による period → (since, until) の変換ロジックを変更しない。

### Requirement 4: 横軸ラベルの月表示

**User Story:** As a セキュリティエンジニア, I want 月単位のときは横軸が年月で表示される, so that どの月のデータか一目で判別できる

#### Acceptance Criteria

1. WHEN Timeline が Monthly_Bucket のデータを表示する, THE Timeline SHALL 横軸ラベルを年月（`YYYY/MM`）形式で表示する。
2. WHEN Timeline が Monthly_Bucket 以外（分 / 15分 / 時間）のデータを表示する, THE Timeline SHALL 横軸ラベルを従来どおり時刻（時:分）形式で表示する。
3. THE Timeline SHALL 各データポイントのプロトコル別内訳（Total / SSH / HTTP）の表示を月単位化によって変更しない。

### Requirement 5: 非機能・スコープ制約

**User Story:** As a 開発者, I want 変更範囲を Timeline の 1y/all 月単位化に限定する, so that 既存機能への副作用を避け、最小差分で安全に修正できる

#### Acceptance Criteria

1. THE 修正 SHALL Timeline_Endpoint 以外のエンドポイント（Summary / Top_IPs / Attack_Types / Severity / Risk_Ranking / Country_Summary）の挙動を変更しない。
2. THE 修正 SHALL Attack_Event の永続データモデル（`attack_events` テーブル）を変更対象としない。
3. THE 修正 SHALL Timeline_Endpoint のレスポンス構造（`timeline` 配列と各要素の `timestamp` / `total` / `ssh` / `http` キー）を変更しない。
4. THE 修正 SHALL `get_timeline` の非 `1y`/`all` 呼び出し（既存の `interval_minutes` に基づく分岐）の挙動を変更しない（後方互換）。
