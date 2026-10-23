# Requirements Document

## Introduction

本修正は、親フェーズ spec [7-feat-http-login-form-collection](../7-feat-http-login-form-collection/requirements.md) および修正 spec [7.01-fix-login-body-preview](../7.01-fix-login-body-preview/requirements.md) で導入した「生のリクエストボディ先頭断片（`body_preview`）」の保持上限を、先頭 1024 バイトから先頭 8192 バイト（8 KB）へ引き上げるものである。

現状、`src/honeywatch/honeypot/http.py` のモジュール定数 `BODY_PREVIEW_LIMIT = 1024` により、全リクエスト経路（`_handle_request` / `_handle_login`）で保存される生ボディは先頭 1024 バイトに切り詰められている。保存処理は共通ヘルパ `_body_preview_from_bytes(body: bytes) -> str | None`（`body[:BODY_PREVIEW_LIMIT]` を UTF-8・デコード不能バイト置換で文字列化、空ボディは `None`）に集約されている。

実運用で観測された RCE 攻撃（例: CVE-2024-4577 を悪用した PHP-CGI argument injection。Base64 でエンコードされた複数コマンドを含む POST ボディ、`Content-Length` が 1 KB を超える）では、先頭 1024 バイトで切り詰められるとペイロードの末尾（最終的なダウンロード元 URL や実行コマンド等）が欠落し、攻撃の全体像を再構成できないという実害がある。

本修正により、`BODY_PREVIEW_LIMIT` を 8192 バイトへ引き上げ、同種の RCE ペイロードを末尾まで保持できるようにする。保存規則（先頭 N バイトを UTF-8・デコード不能バイト置換で文字列化、空ボディは `None`）および適用経路（全経路共通）は変更せず、上限値のみを変更する最小修正とする。

収集データの機密性配慮（product steering: 機密性の高い値を必要以上に保存しない）との整合は、次の切り分けで維持する。

- 生ボディは観測目的で**先頭 8192 バイトまで**に限定して保持する（ボディ全体を溜め込まない）。この上限引き上げ後も「先頭断片のみ保持」という方針は維持する。
- **構造化データ**として保存するのは `email` / `password` の 2 項目のみ（親フェーズ要件 5.1 を維持）。本修正は構造化データの項目を増やさない。
- 1 MB 超のボディは従来どおり拒否する（親フェーズ要件 1.6 / `MAX_BODY_SIZE` を維持）。本修正は読み取り上限（`MAX_BODY_SIZE`）を変更しない。
- password 平文はアプリケーションログに出力しない（親フェーズ要件 5.6 を維持）。`body_preview` は `raw_data`（DB）に保存される値であり、アプリケーションログには出力しない。

## Glossary

- **Body_Preview**: `HTTPEventData.body_preview` フィールド。リクエストボディの先頭 Body_Preview_Limit バイトを UTF-8（デコード不能バイトは置換）で文字列化した観測用の生ボディ断片。
- **Body_Preview_Limit**: `body_preview` に保持する先頭バイト数を表すモジュール定数 `BODY_PREVIEW_LIMIT`。本修正で 1024 から 8192 へ変更する。
- **Body_Preview_Helper**: 生ボディ先頭断片を文字列化する既存のモジュール関数 `_body_preview_from_bytes(body: bytes) -> str | None`。非空なら `body[:BODY_PREVIEW_LIMIT]` を UTF-8（`errors="replace"`）で文字列化し、空ボディは `None` を返す。
- **MAX_BODY_SIZE**: ボディ全体の読み取り上限サイズ（1 MB = 1,048,576 バイト）。親フェーズで導入済み。本修正では変更しない。
- **HTTP_Honeypot**: HTTP Honeypot 実装（`src/honeywatch/honeypot/http.py` の `HTTPHoneypot`）。
- **HTTP_Event_Data**: HTTP リクエスト固有データを表す既存の `HTTPEventData` モデル。
- **Attack_Event**: Honeypot が発行する攻撃イベント共通モデル（既存の `AttackEvent`）。

## Requirements

### Requirement 1: body_preview 保持上限の引き上げ

**User Story:** 攻撃分析者として、1 KB を超える RCE ペイロードの生ボディを末尾まで保持したい。そうすることで、Base64 エンコードされた複数コマンドやダウンロード元 URL を含む攻撃の全体像を後から再構成できる。

#### Acceptance Criteria

1. THE HTTP_Honeypot SHALL Body_Preview_Limit（`BODY_PREVIEW_LIMIT`）を 8192 とする
2. WHEN リクエストの生ボディが Body_Preview_Helper により文字列化される AND 生ボディが 8192 バイトを超える, THE HTTP_Honeypot SHALL 生ボディの先頭 8192 バイトを UTF-8（デコード不能バイトは置換）で文字列化して `raw_data.body_preview` に保存する
3. WHEN リクエストの生ボディが Body_Preview_Helper により文字列化される AND 生ボディが 1 バイト以上 8192 バイト以下である, THE HTTP_Honeypot SHALL 生ボディ全体を UTF-8（デコード不能バイトは置換）で文字列化して `raw_data.body_preview` に保存する
4. IF リクエストの生ボディが空である, THEN THE HTTP_Honeypot SHALL `raw_data.body_preview` を `None` とする（既存挙動を維持する）

### Requirement 2: 既存の保存規則・適用経路の維持

**User Story:** プラットフォーム運用者として、本修正が上限値の変更のみにとどまり、保存規則や適用経路を壊さないことを保証したい。そうすることで、既存の収集・分類・機密性配慮を維持できる。

#### Acceptance Criteria

1. THE HTTP_Honeypot SHALL Body_Preview_Helper の文字列化規則（非空なら先頭 Body_Preview_Limit バイトを `decode("utf-8", errors="replace")`、空ボディは `None`）を上限値以外変更しない
2. THE HTTP_Honeypot SHALL `_handle_request`（/login 以外）と `_handle_login`（POST /login）の両経路が同一の Body_Preview_Helper を用いて `body_preview` を算出する既存構成を維持する
3. THE HTTP_Honeypot SHALL 構造化データとして保存する項目を `email` / `password` の 2 項目のみに限定する既存挙動を維持する（親フェーズ要件 5.1）
4. THE HTTP_Honeypot SHALL password 平文および `body_preview` をアプリケーションログに出力しない既存挙動を維持する（親フェーズ要件 5.6）

### Requirement 3: 読み取り上限（MAX_BODY_SIZE）の不変

**User Story:** プラットフォーム運用者として、本修正がボディ読み取り上限やストレージ方針に影響しないことを保証したい。そうすることで、巨大ボディの溜め込みを引き続き防止できる。

#### Acceptance Criteria

1. THE HTTP_Honeypot SHALL ボディ読み取り上限 `MAX_BODY_SIZE`（1 MB）を変更しない
2. IF 受信したリクエストのボディサイズが MAX_BODY_SIZE を超える, THEN THE HTTP_Honeypot SHALL 親フェーズ要件 1.6 どおり当該ボディを拒否し（POST /login は 413 を返して Attack_Event を発行せず）、`body_preview` も保存しない既存挙動を維持する
