# Implementation Plan: body_preview 保持上限の引き上げ（1024 → 8192）

## Overview

`src/honeywatch/honeypot/http.py` のモジュール定数 `BODY_PREVIEW_LIMIT` を `1024` から `8192` へ変更し、全リクエスト経路（`_handle_request` / `_handle_login`）の生ボディ保持上限を先頭 8192 バイト（8 KB）へ引き上げる。

最小変更方針: 新規コンポーネント・新規依存・DB スキーマ変更・新たな例外経路なし。保持上限はすでに `BODY_PREVIEW_LIMIT` 定数に一元化され、共通ヘルパ `_body_preview_from_bytes` が両経路から参照しているため、定数値の変更のみで両経路に波及する。`_body_preview_from_bytes` のシグネチャ・文字列化規則・呼び出し側は変更しない。

対象ファイル:
- `src/honeywatch/honeypot/http.py`（`BODY_PREVIEW_LIMIT` の値変更、関連コメント/docstring の文言整合）
- `tests/test_honeypot/test_http_login_form.py`（Property / example テスト追記）

## Tasks

- [x] 1. Honeypot: BODY_PREVIEW_LIMIT を 8192 へ引き上げる
  - [x] 1.1 モジュール定数 `BODY_PREVIEW_LIMIT` の値を変更する
    - `src/honeywatch/honeypot/http.py` の `BODY_PREVIEW_LIMIT = 1024` を `BODY_PREVIEW_LIMIT = 8192` に変更する
    - 定数のコメントを、8 KB とする意図（1 KB 超の RCE ペイロードを末尾まで観測。`MAX_BODY_SIZE`（読み取り上限 1 MB）とは別レイヤーの「保存する断片の長さ」）が分かる内容へ更新する
    - `_body_preview_from_bytes` の実装（`body[:BODY_PREVIEW_LIMIT].decode("utf-8", errors="replace")`、空ボディは `None`）は変更しない。docstring 内に「先頭 1024 バイト」等の固定値表現がある場合は定数名に言及する表現へ整合させる（挙動不変の軽微な文言調整）
    - `_handle_request` / `_handle_login` の呼び出し側は変更しない
    - `MAX_BODY_SIZE`・413 経路・構造化2項目限定・ログ出力項目は一切変更しない
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2_

- [x]* 2. テスト: 保持上限引き上げの property / example テスト（親フェーズテストに追記）
  - [x]* 2.1 定数値の検証テスト
    - `tests/test_honeypot/test_http_login_form.py` に追記
    - **Property 1: BODY_PREVIEW_LIMIT は 8192 である**（`from honeywatch.honeypot.http import BODY_PREVIEW_LIMIT` → `== 8192`）
    - **Validates: Requirements 1.1**
  - [x]* 2.2 上限超過ボディの切り詰め property テスト
    - **Property 2: 8192 バイト超は先頭 8192 バイトに切り詰める**（ジェネレータ: 長さ 8193〜十数 KB の `st.binary()`、`_body_preview_from_bytes(b) == b[:8192].decode("utf-8", errors="replace")` を確認、`@settings(max_examples=100)`）
    - **Validates: Requirements 1.2**
  - [x]* 2.3 上限以下ボディの全体保持 property テスト
    - **Property 3: 1〜8192 バイトの非空ボディは全体を保持する**（ジェネレータ: 長さ 1〜8192 の `st.binary()`、`_body_preview_from_bytes(b) == b.decode("utf-8", errors="replace")`（切り詰めなし）を確認、`@settings(max_examples=100)`）
    - **Validates: Requirements 1.3**
  - [x]* 2.4 境界 example テスト（オフバイワン防止）
    - **8192 ちょうど・8193 の境界**: 8192 バイトは全体保持、8193 バイトは先頭 8192 バイトで切れることを example で確認する
    - **Validates: Requirements 1.2, 1.3**
  - [x]* 2.5 空ボディ example テスト（不変の非回帰）
    - **Property 4: 空ボディは None**（`_body_preview_from_bytes(b"") is None`）
    - **Validates: Requirements 1.4**
  - [x]* 2.6 上限超過・413 経路の非回帰 property テスト
    - **Property 5: 1 MB 超 POST は 413・emit なし・保存なし（不変）**（1 MB + 1 の境界で 413・`emit_event` 非呼出・保存なし）
    - **Validates: Requirements 3.1, 3.2**

## Notes

- 新規の外部依存は追加しない（`hypothesis` は既に dev 依存）。
- 本修正は定数値 1 箇所の変更に閉じ、ヘルパ・呼び出し側・読み取り上限（`MAX_BODY_SIZE`）・機密性配慮（構造化2項目限定、ログ非出力）は変更しない。
- 既存レコード（最大 1024 文字相当の `body_preview`）との後方互換は保たれる。スキーマ・読み出し側の変更は不要。
- 変更後は tech steering の手順（`run_checks.sh` に書き出し `.txt` へリダイレクト→read で確認）で `uv run pytest` / `uv run mypy .` / `uv run ruff check src/honeywatch/honeypot/http.py` を実行し、親フェーズ・7.01 の回帰が無いこと・新規テストが全てパスすることを確認する。

## Task Dependency Graph

```
1.1 (定数値変更)
 └─ 2.1〜2.6 (テスト: 任意)
```
