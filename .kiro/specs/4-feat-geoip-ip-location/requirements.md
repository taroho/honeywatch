# Requirements Document

## Introduction

本フィーチャーは、HoneyWatch が観測した攻撃イベントの送信元 IP アドレスを GeoIP（MaxMind GeoLite2）で地理情報（国・地域・都市・緯度・経度）にマッピングし、Dashboard 上で可視化する機能を提供する。

既存の攻撃イベント（`attack_events` テーブル、`source_ip` カラム）には送信元 IP が記録されているが、その IP が「どこの国・地域からのアクセスか」を把握する手段が存在しない。本機能により、攻撃の地理的な傾向を把握し、IP 分析画面・イベント一覧・Top IP・地図表示などで地理情報を確認できるようにする。

本フィーチャーは HoneyWatch 開発フェーズ Phase 3（Security Intelligence）に位置づけられる GeoIP ジオロケーション機能に相当する。GeoIP データベースは MaxMind GeoLite2 を採用する。

地理情報（Geo_Location）は永続的なデータストアに保存せず、GeoIP_Resolver が API リクエストのたびに Source_IP から都度解決するオンザフライ方式を採用する。このため `attack_events` テーブルへの列追加・スキーマ変更・マイグレーションは行わず、すでに記録済みの過去の Attack_Event も記録時期に関わらず Source_IP を都度解決することで新規データと区別なく分析・表示・集計の対象となる。

## Glossary

- **システム**: 本フィーチャーを構成するコンポーネント（GeoIP_Resolver、API_Server、Dashboard）を総称する HoneyWatch 全体。
- **GeoIP_Resolver**: IP アドレスを地理情報に変換するコンポーネント。MaxMind GeoLite2 データベースを参照する。
- **GeoIP_Database**: MaxMind が配布する IP-地理情報マッピングデータ（GeoLite2-City 形式の .mmdb ファイル）。
- **Geo_Location**: IP アドレスに対応する地理情報。国コード（ISO 3166-1 alpha-2）、国名、地域名、都市名、緯度、経度で構成される。
- **API_Server**: Dashboard へデータを提供する FastAPI ベースの REST API サーバー。
- **Dashboard**: React ベースの管理用フロントエンド。攻撃イベントと分析結果を可視化する。
- **Attack_Event**: Honeypot が観測した1回の攻撃的アクセスを表すレコード。`attack_events` テーブルに保存される。
- **Source_IP**: 攻撃イベントの送信元 IP アドレス（`source_ip`）。IPv4 または IPv6 の文字列。
- **Private_IP**: RFC 1918（IPv4）および RFC 4193（IPv6）で定義されるプライベートアドレス、ループバックアドレス等、地理情報を持たない IP アドレス。
- **Geo_Map**: Dashboard 上で攻撃元を地図上のマーカーとして常時表示するコンポーネント。
- **オンザフライ解決**: 地理情報を永続保存せず、要求のたびに GeoIP_Resolver が Source_IP から都度解決する方式。
- **永続的なデータストア**: PostgreSQL 等のデータベースやファイル等、プロセス終了後もデータが残る保存先。Attack_Event を保存する `attack_events` テーブルを含む。

## Requirements

### Requirement 1: GeoIP データベースの読み込み

**User Story:** セキュリティエンジニアとして、MaxMind GeoLite2 データベースを用いて IP を地理情報に変換したい。そうすれば、攻撃元の地理的傾向を把握できる。

#### Acceptance Criteria

1. WHEN API_Server が起動する、THE GeoIP_Resolver SHALL 設定で指定されたパスの GeoIP_Database ファイルを読み込む
2. WHEN GeoIP_Database ファイルの読み込みが正常に完了する、THE GeoIP_Resolver SHALL データベース読み込み済み状態へ遷移し、情報レベルのログを1件出力する
3. WHILE GeoIP_Database が読み込み済み状態である、THE GeoIP_Resolver SHALL 入力された IP アドレスを Geo_Location（国コードおよび都市名を含む）へ変換して返す
4. IF 設定で指定されたパスに GeoIP_Database ファイルが存在しない、THEN THE GeoIP_Resolver SHALL データベース未読み込み状態として初期化し、原因を示すエラーレベルのログを1件出力する
5. IF GeoIP_Database ファイルが存在するが読み込み時に破損または不正な形式で解析に失敗する、THEN THE GeoIP_Resolver SHALL データベース未読み込み状態として初期化し、原因を示すエラーレベルのログを1件出力する
6. WHILE GeoIP_Database が未読み込み状態である、THE GeoIP_Resolver SHALL すべての IP アドレスに対して地理情報なし（未解決を示す null 相当の値）を返す
7. WHERE 入力された IP アドレスが Private_IP（RFC 1918 で定義される 10.0.0.0/8、172.16.0.0/12、192.168.0.0/16 の範囲）である、THE GeoIP_Resolver SHALL データベースを参照せず地理情報なし（未解決を示す null 相当の値）を返す
8. IF 読み込み済み状態で入力された IP アドレスに対応する Geo_Location が GeoIP_Database に存在しない、THEN THE GeoIP_Resolver SHALL 地理情報なし（未解決を示す null 相当の値）を返す
9. THE GeoIP_Database ファイルのパス SHALL 環境変数と `core/config.py` の設定項目で指定できる

### Requirement 2: IP アドレスから地理情報への変換

**User Story:** セキュリティエンジニアとして、送信元 IP から国・地域・都市・緯度経度を取得したい。そうすれば、攻撃元の位置を特定できる。

#### Acceptance Criteria

1. WHEN 有効なパブリック IPv4 または IPv6 アドレスが GeoIP_Resolver に渡される、THE GeoIP_Resolver SHALL 該当する Geo_Location（ISO 3166-1 alpha-2 形式の国コード、国名、地域名、都市名、-90 以上 90 以下の緯度、-180 以上 180 以下の経度）を返す
2. IF GeoIP_Database に該当エントリが存在しない IP アドレスが渡される、THEN THE GeoIP_Resolver SHALL 全フィールドが未設定の地理情報なし（未解決）状態を返し、データベースの内容を変更しない
3. IF Private_IP（RFC 1918 プライベートアドレス、ループバックアドレス、またはリンクローカルアドレス）が GeoIP_Resolver に渡される、THEN THE GeoIP_Resolver SHALL データベース参照を行わず地理情報なし（未解決）を返す
4. IF 形式が不正な IP アドレス文字列（IPv4 または IPv6 として解析できない文字列、空文字列、または null）が GeoIP_Resolver に渡される、THEN THE GeoIP_Resolver SHALL 地理情報なし（未解決）を返し、渡された入力値と不正である旨を示す警告レベルのログを1件出力する
5. WHERE Geo_Location の一部フィールド（例: 都市名、地域名）が GeoIP_Database に存在しない、THE GeoIP_Resolver SHALL 当該フィールドを null として返し、取得できたフィールドは値を保持する
6. IF GeoIP_Database が未初期化またはロードされていない状態で GeoIP_Resolver に IP アドレスが渡される、THEN THE GeoIP_Resolver SHALL データベース参照を行わず地理情報なし（未解決）を返し、データベースが利用不可である旨を示す警告レベルのログを1件出力する

### Requirement 3: 地理情報の API 提供

**User Story:** Dashboard 利用者として、API 経由で IP の地理情報を取得したい。そうすれば、画面上に地理情報を表示できる。

#### Acceptance Criteria

1. WHEN Dashboard が指定した Source_IP の地理情報を要求する、THE API_Server SHALL 当該 IP の Geo_Location（国コード、地域、緯度、経度を含む）を JSON 形式で返す
2. IF 要求された Source_IP の地理情報が未解決である、THEN THE API_Server SHALL Geo_Location の各フィールドを null とした JSON を返す
3. WHEN Dashboard が Top IP 一覧を要求する、THE API_Server SHALL 各 IP エントリに Geo_Location を含め、地理情報が未解決のエントリは Geo_Location の各フィールドを null として返す
4. WHEN Dashboard が国別の攻撃件数集計を要求する、THE API_Server SHALL 国コードごとの Attack_Event 件数を件数の降順、件数が同一の場合は国コードの昇順で並べて返す
5. IF 形式が不正な Source_IP がリクエストパラメータとして渡される、THEN THE API_Server SHALL 当該リクエストを拒否し、不正な IP 形式である旨を示すエラー内容を返し、地理情報は返さない
6. IF GeoIP_Resolver が利用不可である、THEN THE API_Server SHALL Geo_Location の各フィールドを null とした JSON を返し、地理情報が解決できなかった旨を示す
7. WHEN Dashboard が Top IP 一覧を要求する、THE API_Server SHALL Attack_Event 件数の降順で最大 100 件の IP エントリを返す

### Requirement 4: Dashboard での地理情報表示

**User Story:** セキュリティエンジニアとして、Dashboard 上で攻撃元 IP の地理情報を確認したい。そうすれば、攻撃の地理的傾向を視覚的に把握できる。

#### Acceptance Criteria

1. WHEN 利用者が Top IP 一覧を表示する、THE Dashboard SHALL 各 IP の Geo_Location に含まれる ISO 3166-1 alpha-2 形式の国コードおよび国名を表示する
2. WHEN 利用者がイベント一覧を表示する、THE Dashboard SHALL 各イベントの Source_IP に対応する Geo_Location の国コードおよび国名を、表示中の 1 ページあたり最大 100 件のイベントに対して表示する
3. IF 表示対象の Source_IP に対応する Geo_Location が未解決である、THEN THE Dashboard SHALL 当該 IP の地理情報欄に「不明」の固定文言を表示し、当該行の他の項目の表示は維持する
4. IF Source_IP がプライベート IP アドレスまたは予約済み IP アドレスであり Geo_Location を持たない、THEN THE Dashboard SHALL 当該 IP の地理情報欄に「不明」の固定文言を表示する
5. WHEN 利用者が Dashboard で国別の攻撃件数集計を表示する、THE Dashboard SHALL 国ごとの攻撃件数を降順に並べたランキング形式で、上位最大 20 か国を表示する
6. WHILE 国別の攻撃件数集計の対象となる攻撃イベントが 0 件である、THE Dashboard SHALL 国別ランキング領域に集計対象データが存在しない旨の表示を行う
7. WHEN 利用者が Dashboard を表示する、THE Dashboard SHALL Geo_Location の緯度経度を持つ攻撃元 Source_IP を Geo_Map 上のマーカーとして表示する
8. IF Source_IP の Geo_Location に緯度経度が存在しない、THEN THE Dashboard SHALL 当該 IP を Geo_Map 上のマーカーとして表示しない

### Requirement 5: 地理情報の集計・分析

**User Story:** セキュリティエンジニアとして、攻撃を国・地域単位で集計したい。そうすれば、攻撃の発生源を国別に分析できる。

#### Acceptance Criteria

1. WHEN 国別集計が要求される、THE API_Server SHALL 指定された期間内の Attack_Event を ISO 3166-1 alpha-2 形式の国コード単位で集計し、国コードごとの件数を返す
2. WHEN 国別集計結果を返す、THE API_Server SHALL 集計結果を件数の降順で並べ、件数が同一の場合は国コードの昇順で並べる
3. WHEN 国別集計結果を返す、THE API_Server SHALL 最大 1000 件までの国コード区分を返し、それを超える区分は返さない
4. WHEN 国別集計が要求される、THE API_Server SHALL 集計要求の受信から 3 秒以内に集計結果を返す
5. WHERE 期間パラメータが指定されない、THE API_Server SHALL 全期間の Attack_Event を集計対象とする
6. WHEN 期間パラメータが指定される、THE API_Server SHALL ISO 8601 形式で指定された開始日時以上かつ終了日時以下（両端を含む）の Attack_Event を集計対象とする
7. IF 期間パラメータが ISO 8601 形式でない、または開始日時が終了日時より後である、THEN THE API_Server SHALL 集計を行わず、パラメータが不正であることを示すエラー応答を返し、既存データを変更しない
8. IF 集計対象の Attack_Event が 0 件である、THEN THE API_Server SHALL 空の集計結果を返す
9. WHEN 国別集計を行う、THE API_Server SHALL Geo_Location が未解決の Attack_Event を「不明」を表す区分として集計に含める

### Requirement 6: 地理情報の解決方式とデータ範囲

**User Story:** セキュリティエンジニアとして、地理情報を DB に保存せず送信元 IP から都度解決したい。そうすれば、スキーマ変更やバックフィルなしに過去データを含めて地理情報を分析できる。

#### Acceptance Criteria

1. THE システム SHALL 地理情報（Geo_Location）を永続的なデータストアに保存しない
2. THE システム SHALL attack_events テーブルのスキーマを変更しない
3. WHEN 地理情報が要求される、THE システム SHALL 対象の Source_IP を GeoIP_Resolver で都度解決して地理情報を得る
4. WHEN 過去に記録された Attack_Event を含む分析・集計・表示が要求される、THE システム SHALL 記録時期に関わらず当該 Attack_Event の Source_IP を都度解決して地理情報を付与する
