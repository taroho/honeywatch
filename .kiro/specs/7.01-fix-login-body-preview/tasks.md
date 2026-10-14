# Implementation Plan: POST /login での生ボディ保持（body_preview）

## Overview

親フェーズ spec [7-feat-http-login-form-collection](../7-feat-http-login-form-collection/tasks.md) の `HTTPHoneypot._handle_login`（`src/honeywatch/honeypot/http.py`）POST 分岐を変更し、`/login` でも生ボディ先頭 1024 バイトを `HTTPEventData.body_preview` に保持する（構造化フィールド email / password は維持し、両方を保存する）。

最小変更方針: 新規コンポーネント・新規依存・DB スキーマ変更なし。読み取り済みボディ（`_read_body_limited` の戻り値）を再利用し、`_handle_request` と同一規則で `body_preview` を算出する。

対象ファイル:
- `src/honeywatch/honeypot/http.py`（`_body_preview_from_bytes` 追加、`_handle_login` POST 分岐で `body_preview` 設定、任意で `_handle_request` の共通化）
- `tests/test_honeypot/test_http_login_form.py`（Property / example テスト追記）

## Tasks

- [x] 1. Honeypot: 生ボディ先頭断片の共通化と POST /login での保持
  - [x] 1.1 `_body_preview_from_bytes` ヘルパを追加する
    - `src/honeywatch/honeypot/http.py` にモジュール定数 `BODY_PREVIEW_LIMIT = 1024` とモジュール関数 `_body_preview_from_bytes(body: bytes) -> str | None` を追加する（非空なら `body[:BODY_PREVIEW_LIMIT].decode("utf-8", errors="replace")`、空なら `None`）
    - 既存 `_handle_request` のインライン body_preview 算出を本関数呼び出しに置き換える（挙動不変の軽微な共通化。既存の空判定・1024・errors="replace" を保つこと）
    - _Requirements: 1.1, 1.3, 2.5_
  - [x] 1.2 `_handle_login` POST 分岐で `body_preview` を保持する
    - `_read_body_limited` が返した `raw_body`（本分岐到達時は常に `bytes`）を再利用し、`body_preview = _body_preview_from_bytes(raw_body)` を算出する（追加のボディ読み取りはしない）
    - POST 分岐の `HTTPEventData(...)` 生成で `body_preview=None` を `body_preview=body_preview` に変更する。`email` / `password` の設定ロジックは不変（両方保持）
    - 401・`event_type="http_login_attempt"`・`protocol="http"`・`source_ip`/`source_port`/`destination_port`/`method`/`path`・ログ出力項目（email 長・path・status・parsed のみ）は一切変更しない
    - GET 分岐・405・413 経路は変更しない（GET は `body_preview=None` のまま、413 はイベント非発行・保存なし）
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 3.1_

- [ ]* 2. テスト: 生ボディ保持の property / example テスト（親フェーズテストに追記）
  - [ ]* 2.1 非空ボディで body_preview が保持される property テスト
    - `tests/test_honeypot/test_http_login_form.py` に追記
    - **Property 1: POST /login は生ボディ先頭1024バイトを body_preview に保持する**（ジェネレータ: 長さ 1〜数 KB の `st.binary()`、`body_preview == body[:1024].decode("utf-8", errors="replace")` を確認、`@settings(max_examples=100)`）
    - **Validates: Requirements 1.1, 1.4**
  - [ ]* 2.2 空ボディで body_preview が None の example テスト
    - **Property 2: 空ボディの POST /login は body_preview を None にする**（空ボディ POST → `raw_data["body_preview"] is None`）
    - **Validates: Requirements 1.3**
  - [ ]* 2.3 両方保持の property テスト
    - **Property 3: POST /login は email/password と body_preview を同時に保持する**（ジェネレータ: 非空 `st.text()` × 2 を urlencode、`email`/`password` と非 None の `body_preview` が同時に存在、`@settings(max_examples=100)`）
    - **Validates: Requirements 1.1, 1.2**
  - [ ]* 2.4 上限超過で body_preview 非保存の edge テスト
    - **Property 4: 上限超過時は body_preview を保存しない**（1 MB + 1 の境界で 413・emit なし・保存なし）
    - **Validates: Requirements 1.5**
  - [ ]* 2.5 構造化2項目限定の非回帰 property テスト
    - **Property 5: 構造化保存は email/password の2項目のみ（不変）**（ジェネレータ: 余分キーを `st.dictionaries`、構造化は2項目のみ、`@settings(max_examples=100)`）
    - **Validates: Requirements 2.2**
  - [ ]* 2.6 ログ非漏洩・401・event_type の回帰確認
    - 親フェーズの password 平文ログ非漏洩・401・`event_type=http_login_attempt` の既存テストが変更なしでパスし続けることを確認
    - _Requirements: 2.1, 2.3_

- [ ] 3. 最終検証（WSL 手順準拠）
  - [ ] 3.1 検証スクリプトで pytest / mypy / ruff を実行し結果を確認する
    - `run_checks.sh` を作成し `export PATH="$HOME/.local/bin:$PATH"` と `cd <repo>` を含め、`uv run pytest -q` / `uv run mypy .` / `uv run ruff check src/honeywatch/honeypot/http.py` を実行して結果を `checks_out.txt`（`.log` 不可）へリダイレクトし、各終了コードも記録する
    - `wsl bash <repo>/run_checks.sh` で実行後、`.txt` を read で読み取り、親フェーズテストの回帰が無いこと・新規テストが全てパスすることを確認する。失敗があれば修正して再実行する
    - 確認後、検証用スクリプト・`.txt` はユーザーへ削除可否を確認したうえで片付ける
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

## Notes

- `*` 付きサブタスクは任意（テスト）。コア実装（1.1, 1.2）には付与しない。
- 新規の外部依存は追加しない（`hypothesis` は既に dev 依存）。
- 本修正は `_handle_login` POST 分岐に閉じ、`/login` 以外の経路（`_handle_request`）の挙動は変更しない（軽微な共通化を除く）。
- `body_preview` は `raw_data`（DB）にのみ入り、アプリケーションログには出力しない（親フェーズ要件 5.6 を維持）。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["2.1", "2.2", "2.3", "2.4", "2.5", "2.6"] },
    { "id": 3, "tasks": ["3.1"] }
  ]
}
```
