# Requirements Document

## Introduction

本 spec は、親フェーズ `4-feat-geoip-ip-location` で実装済みの GeoIP 機能のうち、Dashboard の攻撃元マップ（Geo_Map）に対する修正である。

現状の Geo_Map は「直近24時間・上位10 IP」に固定されており、期間切り替え UI を持たない。Dashboard は `useGeoTopIPs()`（引数なし: limit=10, period="24h"）の結果を Geo_Map の表示エントリとして渡し、緯度経度を持つ IP をマーカーとして描画している。データ供給元の API `/geo/top-ips` は period パラメータとして `1h`／`6h`／`24h`／`7d` のみを受け付ける。

本修正では、Geo_Map に期間切り替えタブ（`24h`／`7d`／`1y`／`all`）を追加し、選択した期間で集計した攻撃件数上位20 IP をマーカー表示できるようにする。あわせて、API `/geo/top-ips` の period パラメータに `1y`（直近365日）と `all`（全期間、期間フィルタなし）を追加する。

本修正のスコープは「Geo_Map の期間フィルタと表示件数（上限20）の変更、および `/geo/top-ips` の period 拡張」に限定する。国別ランキング（Country_Summary）や Top IP テーブルの仕様変更は含まない。ただし `/geo/top-ips` の period 拡張が他の利用箇所へ影響しないこと（後方互換）は非機能要件として扱う。

## Glossary

親 spec `4-feat-geoip-ip-location` の Glossary を継承する。本修正で参照・追加する主な用語は以下のとおり。

- **Dashboard**: React ベースの管理用フロントエンド。攻撃イベントと分析結果を可視化する。（親 spec より継承）
- **API_Server**: Dashboard へデータを提供する FastAPI ベースの REST API サーバー。（親 spec より継承）
- **Geo_Map**: Dashboard 上で攻撃元を地図上のマーカーとして表示するコンポーネント。（親 spec より継承。親 spec 内の別名 GeoMap と同一）
- **Geo_Location**: Source_IP に対応する地理情報。国コード、国名、地域名、都市名、緯度、経度で構成される。（親 spec より継承）
- **Source_IP**: 攻撃イベントの送信元 IP アドレス。IPv4 または IPv6 の文字列。（親 spec より継承）
- **Attack_Event**: Honeypot が観測した1回の攻撃的アクセスを表すレコード。`attack_events` テーブルに保存される。（親 spec より継承）
- **Top_IPs_Endpoint**: 攻撃件数の多い Source_IP に Geo_Location を付与して返す API エンドポイント `/geo/top-ips`。
- **Period_Tab**: Geo_Map 上部に配置する期間切り替えタブ UI。選択肢は `24h`／`7d`／`1y`／`all` の4つ。
- **Map_Marker**: Geo_Map 上に描画される、緯度経度を持つ Source_IP を表すマーカー。
- **直近1年**: 集計要求時点から遡って365日間を対象とする期間（`1y`）。
- **全期間**: 期間の下限を設けず、対象データすべてを集計対象とする範囲（`all`）。`/geo/top-ips` において開始日時（since）を付与しないことを意味する。

## Requirements

### Requirement 1: Geo_Map の期間切り替えタブ

**User Story:** セキュリティエンジニアとして、攻撃元マップの集計期間を切り替えたい。そうすれば、期間ごとの攻撃元の地理的傾向を確認できる。

#### Acceptance Criteria

1. WHEN 利用者が Dashboard を表示する、THE Dashboard SHALL Geo_Map に期間切り替えタブ（Period_Tab）として `24h`、`7d`、`1y`、`all` の4つの選択肢を表示する
2. WHEN 利用者が Dashboard を初めて表示する、THE Dashboard SHALL Period_Tab の初期選択を `24h` とし、`24h` を集計期間として Geo_Map を表示する
3. WHEN 利用者が Period_Tab のいずれかの期間を選択する、THE Dashboard SHALL 選択された期間を集計期間として Geo_Map の表示を更新する
4. WHILE いずれかの期間が選択されている、THE Dashboard SHALL 選択中の期間タブを未選択の期間タブと区別できる表示状態にする
5. THE Period_Tab SHALL 親 spec で実装済みの Detection Analysis の期間セレクタおよび Severity 別内訳と同一のタブ切り替え方式で表示する

### Requirement 2: 選択期間に応じた上位20 IP のマーカー表示

**User Story:** セキュリティエンジニアとして、選択した期間の攻撃件数上位20の攻撃元を地図で確認したい。そうすれば、期間内で攻撃が集中している送信元を把握できる。

#### Acceptance Criteria

1. WHEN 利用者が Period_Tab で期間を選択する、THE Dashboard SHALL 選択された期間を対象として Top_IPs_Endpoint に limit=20 で集計を要求する
2. WHEN Top_IPs_Endpoint が選択期間の集計結果を返す、THE Dashboard SHALL 攻撃件数の降順で最大20件の Source_IP を Geo_Map の表示対象エントリとする
3. WHEN Geo_Map が表示対象エントリを描画する、THE Dashboard SHALL Geo_Location に緯度経度を持つ Source_IP のみを Map_Marker として描画する
4. IF 表示対象エントリの Source_IP が Geo_Location に緯度経度を持たない、THEN THE Dashboard SHALL 当該 Source_IP を Map_Marker として描画しない
5. IF 選択期間の表示対象エントリのうち緯度経度を持つ Source_IP が0件である、THEN THE Dashboard SHALL Geo_Map 上に表示できる位置情報が存在しない旨の表示を行う

### Requirement 3: Top_IPs_Endpoint の period 拡張

**User Story:** Dashboard 利用者として、`/geo/top-ips` で1年および全期間の集計を要求したい。そうすれば、長期および全期間の攻撃元上位 IP を取得できる。

#### Acceptance Criteria

1. WHEN Dashboard が Top_IPs_Endpoint に period=`1y` を指定して要求する、THE API_Server SHALL 要求受信時点から遡って365日間の Attack_Event を集計対象とし、攻撃件数の降順で上位 IP に Geo_Location を付与して返す
2. WHEN Dashboard が Top_IPs_Endpoint に period=`all` を指定して要求する、THE API_Server SHALL 期間の下限を設けず全期間の Attack_Event を集計対象とし、攻撃件数の降順で上位 IP に Geo_Location を付与して返す
3. WHEN Dashboard が Top_IPs_Endpoint に period=`24h` または period=`7d` を指定して要求する、THE API_Server SHALL 親 spec で実装済みの集計結果と同一の集計対象期間で結果を返す
4. WHEN Dashboard が Top_IPs_Endpoint に limit パラメータを指定して要求する、THE API_Server SHALL 1 以上 100 以下の範囲で指定された件数を上限として上位 IP を返す
5. IF Dashboard が Top_IPs_Endpoint に `1h`、`6h`、`24h`、`7d`、`1y`、`all` のいずれにも一致しない period を指定して要求する、THEN THE API_Server SHALL 当該要求を拒否し、period が不正である旨を示すエラー応答を返す
6. WHEN Top_IPs_Endpoint が Geo_Location が未解決の Source_IP を含む集計結果を返す、THE API_Server SHALL 当該エントリの Geo_Location の各フィールドを null として返す

### Requirement 4: 既存利用箇所への後方互換

**User Story:** 開発者として、`/geo/top-ips` の period 拡張が既存の利用箇所を壊さないことを保証したい。そうすれば、今回の修正による回帰を防げる。

#### Acceptance Criteria

1. THE API_Server SHALL Top_IPs_Endpoint の period パラメータの既定値を `24h` として維持する
2. THE API_Server SHALL Top_IPs_Endpoint の limit パラメータの既定値を 10、許容範囲を 1 以上 100 以下として維持する
3. WHEN period パラメータを指定せずに Top_IPs_Endpoint が要求される、THE API_Server SHALL 直近24時間を集計対象として親 spec と同一の結果を返す
4. THE API_Server SHALL Country_Summary エンドポイントおよび Top IP テーブル向けエンドポイントの集計仕様を本修正によって変更しない
