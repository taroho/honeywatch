# Requirements Document

## Introduction

本修正は、親フェーズ spec [7-feat-http-login-form-collection](../7-feat-http-login-form-collection/requirements.md) で実装した HTTP ログインフォーム認証情報収集機能に対し、`/login` 経路でも「生のリクエストボディの先頭断片（`body_preview`）」を保持するように挙動を変更するものである。

親フェーズの実装では、`/login` の GET / POST いずれも `HTTPEventData.body_preview` を `None` に設定しており、ログイン経路の生ボディが一切保存されていなかった。一方、`/login` 以外の全リクエスト経路（`_handle_request`）では従来どおりボディ先頭 1024 バイトを `body_preview` に保持している。

Honeypot の目的は「攻撃者が実際に投げてきた生のペイロードを忠実に観測する」ことにある。ログイン経路だけ生ボディを落とすと、次の観測価値が失われる。

- 攻撃者が送信した `email` / `password` 以外のフィールド（CSRF トークン・リダイレクト先・ツール固有パラメータ等）の痕跡
- ボディのエンコード形式・構造の癖（攻撃ツールのフィンガープリント）
- 後からの再分析（構造化データだけでは email/password 以外を掘れない）

本修正により、`/login` 経路でも他の全経路と一貫して生ボディ先頭 1024 バイトを `body_preview` に保持しつつ、親フェーズで導入した構造化フィールド（`email` / `password`）も引き続き保持する（両方保持）。

収集データの機密性配慮（product steering: 機密性の高い値を必要以上に保存しない）との整合は、次の切り分けで維持する。

- **構造化データ**として保存するのは `email` / `password` の 2 項目のみ（親フェーズ要件 5.1 を維持。生ボディは構造化データではない）。
- 生ボディは観測目的で**先頭 1024 バイトまで**に限定して保持する（ボディ全体を溜め込まない）。
- 1 MB 超のボディは従来どおり拒否する（親フェーズ要件 1.6 を維持）。
- password 平文はアプリケーションログに出力しない（親フェーズ要件 5.6 を維持）。`body_preview` は `raw_data`（DB）に保存される値であり、アプリケーションログには出力しない。

## Glossary

- **Login_Endpoint**: ログインフォームの送信先 HTTP パス（`/login`）。親フェーズと同一。
- **Body_Preview**: `HTTPEventData.body_preview` フィールド。リクエストボディの先頭 1024 バイトを UTF-8（デコード不能バイトは置換）で文字列化した観測用の生ボディ断片。
- **HTTP_Event_Data**: HTTP リクエスト固有データを表す既存の `HTTPEventData` モデル。
- **Attack_Event**: Honeypot が発行する攻撃イベント共通モデル（既存の `AttackEvent`）。
- **MAX_BODY_SIZE**: ボディ全体の上限サイズ（1 MB = 1,048,576 バイト）。親フェーズで導入済み。
- **Body_Preview_Limit**: `body_preview` に保持する先頭バイト数（1024 バイト）。既存の `_handle_request` と同一値。

## Requirements

### Requirement 1: POST /login での生ボディ保持

**User Story:** 攻撃分析者として、ログインフォームに POST されたリクエストの生ボディ先頭断片も保持したい。そうすることで、email / password 以外のフィールドやボディ構造を後から分析できる。

#### Acceptance Criteria

1. WHEN POST リクエストが Login_Endpoint に対して受信され、ボディサイズが MAX_BODY_SIZE 以下である, THE HTTP_Honeypot SHALL 当該リクエストの生ボディ先頭 Body_Preview_Limit（1024 バイト）を UTF-8（デコード不能バイトは置換）で文字列化し、Attack_Event の `raw_data.body_preview` に保存する
2. WHEN POST /login の生ボディ先頭断片を保存する, THE HTTP_Honeypot SHALL 親フェーズで導入した構造化フィールド `email` / `password` の保存を従来どおり維持する（両方を保持する）
3. IF POST /login のリクエストボディが空である, THEN THE HTTP_Honeypot SHALL `raw_data.body_preview` を `None` とする（親フェーズの `_handle_request` の空ボディ時挙動と一致させる）
4. WHEN POST /login の生ボディを `body_preview` に保存する, THE HTTP_Honeypot SHALL 既に読み取り済みのボディバイト列を再利用し、追加のボディ読み取りを行わない
5. IF 受信した POST /login リクエストのボディサイズが MAX_BODY_SIZE を超える, THEN THE HTTP_Honeypot SHALL 親フェーズ要件 1.6 どおり 413 を返して Attack_Event を発行せず、`body_preview` も保存しない

### Requirement 2: 既存挙動の維持

**User Story:** プラットフォーム運用者として、本修正が親フェーズの他の挙動を壊さないことを保証したい。そうすることで、既存の収集・分類・機密性配慮を維持できる。

#### Acceptance Criteria

1. THE HTTP_Honeypot SHALL POST /login で発行する Attack_Event の `event_type` を `http_login_attempt`、`protocol` を `http`、ステータスコードを 401 とする既存挙動を維持する
2. THE HTTP_Honeypot SHALL 構造化データとして保存する項目を `email` / `password` の 2 項目のみに限定する既存挙動を維持する（親フェーズ要件 5.1）。生ボディの `body_preview` 保持は構造化データ保存には該当しない
3. THE HTTP_Honeypot SHALL password 平文をアプリケーションログに出力しない既存挙動を維持する（親フェーズ要件 5.6）。`body_preview` はログ出力しない
4. THE HTTP_Honeypot SHALL `source_ip` / `source_port` / `destination_port` / `method` / `path` の記録を従来どおり維持する（親フェーズ要件 3.5）
5. WHERE リクエストパスが Login_Endpoint 以外である, THE HTTP_Honeypot SHALL 既存の `_handle_request` の `body_preview` 挙動（先頭 1024 バイト保持）を一切変更しない

### Requirement 3: GET /login の扱い

**User Story:** 攻撃分析者として、GET /login の `body_preview` 挙動が過剰にならないようにしたい。そうすることで、ボディを持たない GET で不要な保存を避けられる。

#### Acceptance Criteria

1. WHEN GET リクエストが Login_Endpoint に対して受信される, THE HTTP_Honeypot SHALL `raw_data.body_preview` を `None` のままとする（GET は通常ボディを持たないため、本修正の対象は POST とする）
