# Requirements Document

## Introduction

本機能は、既存の HTTP Honeypot に「email と password だけの簡易ログインフォーム」を提供し、攻撃者がそのフォームに送信した認証情報（email / password）を攻撃イベントとして収集・保存できるようにするものである。

HoneyWatch は Honeypot ベースの攻撃監視・分析プラットフォームであり、既に SSH Honeypot では認証試行の username / password を収集している。本機能は HTTP 経由の認証情報収集（Credential Attack の観測）を可能にし、Web ベースの資格情報詐取を狙う攻撃の分析対象を広げることを目的とする。

実装にあたっては、既存の `HTTPHoneypot`（`src/honeywatch/honeypot/http.py`）、イベントモデル（`src/honeywatch/collector/events.py`）、イベント発行基盤（`BaseHoneypot.emit_event`）、攻撃分類エンジン（`src/honeywatch/detection/classifier.py`）、検知ルール（`src/honeywatch/detection/patterns.py` / `config/detection_rules.yaml`）、DB モデル（`src/honeywatch/db/models.py`）を優先的に活用する前提とする。

収集した認証情報の取り扱いは、product steering のセキュリティ方針（機密性の高い値を必要以上に保存しない）に配慮する。本 Honeypot が受け取る値は実在ユーザーの正規資格情報ではなく、攻撃者が投入した攻撃ペイロードであるため、SSH Honeypot と同様に分析目的で平文保持するが、保持範囲は email / password の2項目に限定し、長さ上限を設ける。

## Glossary

- **HTTP_Honeypot**: 既存の `HTTPHoneypot` クラス。aiohttp で HTTP サーバーを模倣し、全リクエストを攻撃イベントとして記録するコンポーネント。
- **Login_Form**: HTTP_Honeypot が提供する、email フィールドと password フィールドのみを持つ簡易 HTML ログインフォーム。
- **Login_Endpoint**: Login_Form の送信先となる HTTP パス（`/login`）。
- **Credential_Submission**: 攻撃者が Login_Form に入力し POST 送信した email / password の組。
- **HTTP_Event_Data**: HTTP リクエスト固有データを表す既存の `HTTPEventData` モデル。
- **Attack_Event**: Honeypot が発行する攻撃イベント共通モデル（既存の `AttackEvent`）。
- **Event_Queue**: イベント投入先の既存 `EventQueue`（`BaseHoneypot.emit_event` 経由で使用）。
- **Attack_Classifier**: 攻撃イベントを攻撃タイプ・Severity に分類する既存エンジン `AttackClassifier`。
- **Credential_Attack**: 認証情報を狙った攻撃を表す既存の攻撃タイプ定数 `credential_attack`。
- **Detection_Rules**: `config/detection_rules.yaml` から読み込む検知ルール（既存 `DetectionRules`）。
- **Max_Credential_Length**: Credential_Submission の各フィールド（email / password）について保存時に適用する最大文字数。既定値は 256 文字。設定により 1 文字以上 4096 文字以下の整数値を指定でき、無効な値が指定された場合は既定値 256 文字にフォールバックする。

## Requirements

### Requirement 1: 簡易ログインフォームの提供

**User Story:** 攻撃者を誘引する運用者として、HTTP Honeypot に email と password だけの簡易ログインフォームを表示させたい。そうすることで、Web ベースの資格情報詐取を狙う攻撃を観測できる。

#### Acceptance Criteria

1. WHEN GET リクエストが Login_Endpoint に対して受信される, THE HTTP_Honeypot SHALL email 入力フィールドと password 入力フィールドのみ（他の入力フィールドを含まない）を持つ Login_Form を含む HTTP レスポンスを、ステータスコード 200 で返す
2. THE Login_Form SHALL email フィールドの入力名を `email`、password フィールドの入力名を `password` とする
3. THE Login_Form SHALL POST メソッドで Login_Endpoint へ送信する単一の form 要素を含む
4. WHEN GET リクエストが Login_Endpoint に対して受信される, THE HTTP_Honeypot SHALL 既存の偽装サーバーヘッダー（`Server`, `X-Powered-By`）を付与したレスポンスを返す
5. WHEN POST リクエストが Login_Endpoint に対して受信される, THE HTTP_Honeypot SHALL 送信された資格情報（`email`, `password` の各値）を攻撃イベントとして記録し、認証失敗を模すステータスコード 401 のレスポンスを返す
6. IF 受信した GET または POST リクエストのボディサイズが 1 MB（1,048,576 バイト）を超える, THEN THE HTTP_Honeypot SHALL リクエストを拒否したことを示すエラーレスポンスを返し、超過分のボディを永続化しない
7. IF Login_Endpoint に対して GET および POST 以外の HTTP メソッドのリクエストが受信される, THEN THE HTTP_Honeypot SHALL 当該メソッドが許可されないことを示すエラーレスポンスを返す

### Requirement 2: 送信された認証情報の抽出

**User Story:** 攻撃分析者として、ログインフォームに送信された email と password を構造化して取得したい。そうすることで、攻撃者が試行した資格情報を分析できる。

#### Acceptance Criteria

1. WHEN POST リクエストが Login_Endpoint に対して受信され、かつボディが form 形式として解析可能である, THE HTTP_Honeypot SHALL リクエストボディから `email` フィールドと `password` フィールドの値を抽出し、両フィールドを含む Credential_Submission を生成する
2. IF POST リクエストのボディに `email` フィールドが存在しない、または `email` フィールドの値が空である, THEN THE HTTP_Honeypot SHALL Credential_Submission の email を空文字列（長さ 0）として設定する
3. IF POST リクエストのボディに `password` フィールドが存在しない、または `password` フィールドの値が空である, THEN THE HTTP_Honeypot SHALL Credential_Submission の password を空文字列（長さ 0）として設定する
4. WHEN Credential_Submission の email または password の文字数が Max_Credential_Length（256 文字）を超える, THE HTTP_Honeypot SHALL 当該フィールドの値を先頭 Max_Credential_Length 文字に切り詰め、切り詰め後の文字数を Max_Credential_Length 以下にする
5. IF POST リクエストのボディが form 形式として解析できない, THEN THE HTTP_Honeypot SHALL Credential_Submission の email と password をいずれも空文字列（長さ 0）として設定し、当該リクエストの記録処理を中断せず継続する
6. WHEN Credential_Submission が生成される, THE HTTP_Honeypot SHALL 抽出された password の値を平文の原文のまま Credential_Submission に保持する

### Requirement 3: 認証情報イベントの記録

**User Story:** 攻撃分析者として、送信された認証情報を既存のイベント収集基盤を通じて保存したい。そうすることで、他の攻撃イベントと同じ仕組みで検索・分析できる。

#### Acceptance Criteria

1. WHEN Login_Endpoint への POST リクエストから Credential_Submission が抽出される, THE HTTP_Honeypot SHALL `protocol` を `http` に設定した Attack_Event を 1 件生成し Event_Queue へ発行する
2. WHEN Login_Endpoint への POST に対して Attack_Event が生成される, THE HTTP_Honeypot SHALL 当該 Attack_Event の `event_type` を `http_login_attempt` に設定する
3. WHEN Login_Endpoint への POST に対して Attack_Event が生成される, THE HTTP_Honeypot SHALL 抽出した email と password を HTTP_Event_Data の構造化フィールドとして当該 Attack_Event の `raw_data` に含める
4. IF POST リクエストから email または password を抽出できない, THEN THE HTTP_Honeypot SHALL 抽出できなかったフィールドを欠損を示す値（null）として `raw_data` に設定し、Attack_Event の生成と Event_Queue への発行を継続する
5. WHEN Attack_Event が生成される, THE HTTP_Honeypot SHALL 既存の `source_ip`, `source_port`, `destination_port`, `method`, `path` の記録を従来どおり維持する
6. WHILE Event_Queue への発行が接続エラーで失敗している, THE HTTP_Honeypot SHALL 既存のメモリバッファ機構を用いて当該 Attack_Event を一時保持する

### Requirement 4: HTTP 認証情報攻撃の分類

**User Story:** 攻撃分析者として、HTTP ログインフォームへの認証情報送信を Credential Attack として分類したい。そうすることで、ダッシュボードで Credential Attack の傾向を把握できる。

#### Acceptance Criteria

1. WHEN `event_type` が `http_login_attempt` の Attack_Event が分類される, THE Attack_Classifier SHALL 当該イベントを Credential_Attack の分類候補として評価する
2. WHERE Detection_Rules が HTTP の Credential_Attack 判定を有効化している, WHEN `event_type` が `http_login_attempt` の Attack_Event が分類される, THE Attack_Classifier SHALL email フィールドまたは password フィールドが既知の弱い資格情報リストのいずれかの値と完全一致する場合に当該イベントを Credential_Attack に分類する
3. IF `event_type` が `http_login_attempt` の Attack_Event において email フィールドおよび password フィールドのいずれも既知の弱い資格情報リストの値と一致しない, THEN THE Attack_Classifier SHALL 当該イベントを Credential_Attack に分類せず、分類処理を正常に完了する
4. IF `event_type` が `http_login_attempt` の Attack_Event において email フィールドおよび password フィールドの双方が欠落している、もしくは空文字列である, THEN THE Attack_Classifier SHALL 当該イベントを Credential_Attack に分類せず、分類処理を正常に完了する
5. WHEN HTTP の Credential_Attack 判定を追加する, THE Attack_Classifier SHALL SSH 由来の Attack_Event に対する既存の Credential_Attack 判定結果を変更しない

### Requirement 5: 収集データの機密性配慮

**User Story:** プラットフォーム運用者として、収集する認証情報を必要最小限に抑えたい。そうすることで、機密性の高いデータの保持リスクを低減できる。

#### Acceptance Criteria

1. WHEN Login_Endpoint への POST を受信する, THE HTTP_Honeypot SHALL 当該リクエストボディのうち email と password の2項目のみを構造化データとして保存し、それ以外のフィールドは構造化データとして保存しない
2. THE HTTP_Honeypot SHALL Max_Credential_Length の既定値を 256 文字とする
3. WHERE 設定により Max_Credential_Length が 1 文字以上 4096 文字以下の整数値で指定される, THE HTTP_Honeypot SHALL 当該設定値を email および password 各フィールドの切り詰め上限として適用する
4. IF 設定された Max_Credential_Length が 1 文字未満または 4096 文字超、もしくは整数以外である, THEN THE HTTP_Honeypot SHALL 当該設定値を無効として既定値 256 文字を適用する
5. WHEN email または password の文字数が適用中の Max_Credential_Length を超過する, THE HTTP_Honeypot SHALL 当該フィールドを Max_Credential_Length の文字数まで切り詰めて保存する
6. WHEN Credential_Submission を含む Attack_Event をログ出力する, THE HTTP_Honeypot SHALL password の平文値をアプリケーションログに出力しない
