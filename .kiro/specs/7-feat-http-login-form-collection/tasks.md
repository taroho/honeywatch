# Implementation Plan: HTTP ログインフォーム認証情報収集

## Overview

既存コンポーネント（`HTTPHoneypot` / `HTTPEventData` / `BaseHoneypot.emit_event` / `AttackClassifier` / `CredentialAttackRule` / `AttackEventModel`）を優先活用し、新規の外部依存を追加せずに「email と password だけの簡易ログインフォーム」を実装する。

実装は下位の純粋ロジック（設定クランプ → イベントデータモデル拡張 → 検知ルール拡張）から積み上げ、次に Honeypot のリクエスト処理分岐（抽出・切り詰め・イベント発行）、最後に分類器の HTTP 対応へと進める。各ステップは直前のステップの成果物を利用し、孤立コードを残さない。テストは hypothesis による Property-Based Testing（`@settings(max_examples=100)` 以上）と example/edge テストを、該当する実装タスクの直後にサブタスクとして配置する。

対象ファイル:
- `src/honeywatch/core/config.py`（`CredentialSettings` 追加）
- `src/honeywatch/collector/events.py`（`HTTPEventData` 拡張）
- `src/honeywatch/detection/patterns.py`（`CredentialAttackRule` 拡張）
- `config/detection_rules.yaml`（HTTP ルール追記）
- `src/honeywatch/honeypot/http.py`（ログインフォーム処理）
- `src/honeywatch/detection/classifier.py`（HTTP 分類対応）
- `tests/`（Property / example / edge テスト追加）

## Tasks

- [x] 1. 設定レイヤー: Max_Credential_Length のクランプ実装
  - [x] 1.1 `CredentialSettings` と `get_max_credential_length` を追加する
    - `src/honeywatch/core/config.py` に `CredentialSettings`（`env_prefix="CREDENTIAL_"`、`max_credential_length_raw: int = 256`、`max_credential_length` property で 1〜4096 の範囲検証・無効時 256 フォールバック）を追加する
    - `Settings` に `credential: CredentialSettings = CredentialSettings()` を組み込む
    - 設定読み取り/検証失敗時に 256 を返すフォールバック補助関数 `get_max_credential_length()` を追加する（非整数文字列による `ValidationError` も捕捉）
    - _Requirements: 5.2, 5.3, 5.4_
  - [x]* 1.2 Max_Credential_Length クランプの property テストを書く
    - 新規 `tests/test_core/test_credential_settings.py` に実装
    - **Property 10: Max_Credential_Length は有効範囲にクランプされる**（ジェネレータ: `st.integers()`、`@settings(max_examples=100)`）
    - **Validates: Requirements 5.2, 5.3, 5.4**
  - [x]* 1.3 Max_Credential_Length の example テストを書く
    - 環境変数未設定で `get_max_credential_length() == 256`、非整数文字列設定時のフォールバックが 256 になることを確認
    - _Requirements: 5.2, 5.4_

- [x] 2. イベントデータモデル: HTTPEventData の後方互換拡張
  - [x] 2.1 `HTTPEventData` に email / password フィールドを追加する
    - `src/honeywatch/collector/events.py` の `HTTPEventData` に `email: str | None = Field(default=None, ...)` と `password: str | None = Field(default=None, ...)` を追加する
    - 既存の `http_request` / `ssh_*` イベントで None となり後方互換が保たれること（`model_dump()` 形状がキー追加のみ）を設計どおりに保つ
    - _Requirements: 3.3, 3.4_

- [x] 3. 検知ルール: CredentialAttackRule の HTTP 対応
  - [x] 3.1 `CredentialAttackRule` に HTTP 用フィールドを追加する
    - `src/honeywatch/detection/patterns.py` の `CredentialAttackRule` に `http_enabled: bool = True` と `emails: list[str] = Field(default_factory=list)` をデフォルト付きで追加する（YAML 未指定でもデフォルトが効き既存ファイルと後方互換）
    - _Requirements: 4.2_
  - [x] 3.2 `detection_rules.yaml` に HTTP ルールを追記する
    - `config/detection_rules.yaml` の `credential_attack` に `http_enabled` と `emails`（既知の弱い email リスト）を追記する（`passwords` は SSH と共用）
    - _Requirements: 4.1, 4.2_

- [x] 4. Honeypot: 認証情報の抽出・切り詰め（純粋ロジック）
  - [x] 4.1 `_truncate` と `CredentialSubmission`、`_extract_credentials` を実装する
    - `src/honeywatch/honeypot/http.py` に `_truncate(value, limit)`（先頭 limit 文字へ切り詰め、コードポイント単位）を追加する
    - `CredentialSubmission`（`dataclass`、`email: str` / `password: str` / `parsed: bool`）を追加する
    - `_extract_credentials(raw_body)` を `urllib.parse.parse_qs`（標準ライブラリ）で実装する: form 解析可能なら email/password を抽出・`get_max_credential_length()` で切り詰め、欠落/空は空文字、`Content-Type` が form でない・解析不能時は email/password とも空文字で `parsed=False` とし例外を送出しない
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_
  - [x]* 4.2 切り詰めの property テストを書く
    - `tests/test_honeypot/test_http_login_form.py`（新規）に実装
    - **Property 4: 切り詰めは長さ上限を保ちつつ先頭を保存する**（ジェネレータ: `st.text()`, `st.integers(1, 4096)`、`@settings(max_examples=100)`）
    - **Validates: Requirements 2.4, 5.5**
  - [x]* 4.3 form 抽出 round-trip の property テストを書く
    - **Property 2: form 抽出の round-trip（切り詰め範囲内で入力を復元）**（ジェネレータ: 長さ ≤ limit の `st.text()` を urlencode、`@settings(max_examples=100)`）
    - **Validates: Requirements 2.1**
  - [x]* 4.4 欠落・空フィールドの property テストを書く
    - **Property 3: 欠落・空フィールドは空文字になる**（ジェネレータ: email/password の片方欠落・空を含むボディ生成、`@settings(max_examples=100)`）
    - **Validates: Requirements 2.2, 2.3**
  - [x]* 4.5 form 解析失敗の edge テストを書く
    - 非 form ボディ（ランダムバイト・JSON・空）で `email == ""` / `password == ""` / `parsed == False` となり例外を送出しないことを確認
    - _Requirements: 2.5_

- [x] 5. Checkpoint - 下位ロジックのテストが通ることを確認
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Honeypot: ログインフォーム提供とリクエスト処理分岐
  - [x] 6.1 `/login` 専用分岐とフォーム・メソッド・サイズ制御を実装する
    - `src/honeywatch/honeypot/http.py` に `HTML_LOGIN_EMAIL`（email/password のみの単一 form、`method="POST" action="/login"`）、`MAX_BODY_SIZE = 1_048_576`、`LOGIN_ALLOWED_METHODS = {"GET", "POST"}` を追加する
    - `ADMIN_PATHS` から `/login` を除外し、他の管理系パス（`/admin` 等）の既存 401 挙動は維持する
    - `_handle_request` 冒頭で path を正規化し `/login` を判定して `_handle_login` へ委譲する（それ以外のパスは既存処理のまま挙動不変）
    - `_read_body_limited(request)` を実装し `Content-Length` と逐次読み取りの両方を `MAX_BODY_SIZE` で打ち切り、超過時 `None`、読み取り例外時は空ボディ扱いで継続する
    - `_handle_login(request)` を実装: GET は `HTML_LOGIN_EMAIL` を 200 + `FAKE_SERVER_HEADERS` で返す、GET/POST 以外は 405、ボディ超過は 413（イベント発行しない）
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6, 1.7_
  - [ ]* 6.2 ログインフォーム提供の example テストを書く
    - GET /login で status==200、本文の input name 集合 == `{"email", "password"}`（他の入力名を含まない）、`<form method="POST" action="/login">` が単一、`Server` / `X-Powered-By` ヘッダー付与を確認
    - _Requirements: 1.1, 1.2, 1.3, 1.4_
  - [ ]* 6.3 ボディサイズ境界の edge テストを書く
    - 1 MB ちょうど → 受理・emit あり、1 MB + 1 → 413・emit なしを確認
    - _Requirements: 1.6_
  - [ ]* 6.4 許可メソッドの property/列挙テストを書く
    - GET/POST を除くメソッド集合（`PUT` / `DELETE` / `PATCH` / `HEAD` / `OPTIONS` 等）から `st.sampled_from` で 405 を確認（`@settings(max_examples=100)`）
    - _Requirements: 1.7_

- [x] 7. Honeypot: 認証情報イベントの生成と発行
  - [x] 7.1 POST /login でイベントを生成し発行して 401 を返す
    - `_handle_login` の POST 分岐で `_extract_credentials` の結果から `HTTPEventData`（存在かつ非空のときのみ email/password を str 設定、それ以外は None）を構築する
    - `event_type="http_login_attempt"` / `protocol="http"` の `AttackEvent` を 1 件生成し `source_ip` / `source_port` / `destination_port` / `method` / `path` を従来どおり設定、`self.emit_event(event)` を呼び、発行後に 401 + `HTML_LOGIN_EMAIL` を返す
    - `logger` 出力は email 長・path・status・エラー種別のみとし、password 平文および email 値そのものを出力しない
    - _Requirements: 1.5, 3.1, 3.2, 3.3, 3.4, 3.5, 5.1, 5.6_
  - [ ]* 7.2 POST→単一イベント発行・401 の property テストを書く
    - **Property 1: ログイン POST は常に単一の http_login_attempt イベントを発行し 401 を返す**（ジェネレータ: `st.text()` × 2、`emit_event` を `AsyncMock`、`@settings(max_examples=100)`）
    - **Validates: Requirements 1.5, 3.1, 3.2, 2.6**
  - [ ]* 7.3 raw_data 構造化反映の property テストを書く
    - **Property 5: 抽出した認証情報は raw_data に構造化反映される**（ジェネレータ: 非空 `st.text()` × 2、`@settings(max_examples=100)`）
    - **Validates: Requirements 3.3**
  - [ ]* 7.4 構造化保存は 2 項目のみの property テストを書く
    - **Property 9: 構造化保存されるのは email / password の 2 項目のみ**（ジェネレータ: email/password + 余分キーを `st.dictionaries`、`@settings(max_examples=100)`）
    - **Validates: Requirements 5.1**
  - [ ]* 7.5 password 平文のログ非漏洩 property テストを書く
    - **Property 11: password 平文はアプリケーションログに出力されない**（ジェネレータ: 十分な長さ・一意性の `st.text(min_size=1)`、`structlog.testing.capture_logs` または `caplog` で全ログに平文が現れないことを確認、`@settings(max_examples=100)`）
    - **Validates: Requirements 5.6**
  - [x]* 7.6 欠損 null・接続エラー・基本フィールドの example/edge テストを書く
    - 非 form ボディで `raw_data` の email/password が None かつ emit が呼ばれ処理継続（_Requirements: 3.4_）
    - `publish` が `ConnectionError` を送出するモックで `_buffer` に 1 件積まれる（_Requirements: 3.6_）
    - イベントに `source_ip` / `source_port` / `destination_port` / `method` / `path` が設定されている（_Requirements: 3.5_）
    - _Requirements: 3.4, 3.5, 3.6_

- [ ] 8. Checkpoint - Honeypot のテストが通ることを確認
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. 分類器: HTTP 認証情報攻撃の分類と SSH 回帰防止
  - [ ] 9.1 `_is_credential_attack` を protocol 分岐に変更する
    - `src/honeywatch/detection/classifier.py` の `_is_credential_attack` を protocol 分岐へ変更する: `ssh` は既存ロジック（`username in rule.usernames` または `password in rule.passwords`）を完全温存
    - `http` かつ `event_type == "http_login_attempt"` のとき、`rule.http_enabled` が True であれば非空 email が `rule.emails` に、または非空 password が `rule.passwords` に完全一致する場合に credential_attack と判定、`http_enabled` が False・空文字・None は非該当
    - `http_request`（通常）は従来どおり credential_attack に該当しない
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
  - [ ]* 9.2 弱資格情報一致の property テストを書く
    - `tests/test_detection/test_classifier.py` に追記（既存 `rules` / `classifier` フィクスチャ再利用、`http_enabled` / `emails` を加えたルール）
    - **Property 6: 弱い資格情報を含む http_login_attempt は credential_attack に分類される**（ジェネレータ: 弱リストから `st.sampled_from`、`@settings(max_examples=100)`）
    - **Validates: Requirements 4.1, 4.2**
  - [ ]* 9.3 弱資格情報非一致の property テストを書く
    - **Property 7: 弱い資格情報に一致しない http_login_attempt は credential_attack に分類されない**（ジェネレータ: 弱リスト外になるよう `assume`、`@settings(max_examples=100)`）
    - **Validates: Requirements 4.3, 4.4**
  - [ ]* 9.4 SSH 判定不変の property テストを書く
    - **Property 8: SSH イベントの credential_attack 判定は不変**（ジェネレータ: `st.text()` × 2、弱リスト値も混在、既存ロジックと判定一致を確認、`@settings(max_examples=100)`）
    - **Validates: Requirements 4.5**
  - [ ]* 9.5 欠損・空の分類 edge テストを書く
    - email/password が None / "" の各組み合わせの http_login_attempt で分類結果が credential_attack 以外になることを確認
    - _Requirements: 4.4_
  - [ ]* 9.6 既存 SSH 分類テストの回帰確認を行う
    - 既存 `test_credential_attack_by_username` 等の SSH 分類テストを変更せず全てパスすることを確認（要件 4.5 の回帰防止）
    - _Requirements: 4.5_

- [ ] 10. 最終検証（WSL 手順準拠）
  - [ ] 10.1 検証スクリプトで pytest / mypy / ruff を実行し結果を確認する
    - `run_checks.sh` を作成し `export PATH="$HOME/.local/bin:$PATH"` と `cd <repo>` を含め、`uv run pytest -q` / `uv run mypy .` / `uv run ruff check <変更ファイル>` を実行して結果を `checks_out.txt`（`.log` 不可）へリダイレクトし、各終了コードも記録する
    - `wsl bash <repo>/run_checks.sh` で実行後、`.txt` を read で読み取り、既存テストの回帰が無いこと・新規テストが全てパスすることを確認する。失敗があれば修正して再実行する
    - 確認後、検証用スクリプト・`.txt` はユーザーへ削除可否を確認したうえで片付ける
    - _Requirements: 4.5_

## Notes

- `*` 付きサブタスクは任意（テスト）であり、MVP を急ぐ場合にスキップ可能。コア実装タスクには付与しない。
- 各タスクはトレーサビリティのため具体的な要件番号を参照する。
- Checkpoint で段階的に検証する。
- Property テストは設計の正しさプロパティ（Property 1〜11）を網羅し、`@settings(max_examples=100)` 以上で反復する。
- example / edge テストは固定テンプレート（1.1〜1.4）・境界（1.6）・既存機構の再利用（3.6）・欠損 null（3.4）・SSH 回帰（4.5）を補完する。
- 新規の外部依存は追加しない（`hypothesis` は既に dev 依存）。form 解析は標準ライブラリ `urllib.parse.parse_qs` を用いる。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "2.1", "3.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "3.2", "4.1"] },
    { "id": 2, "tasks": ["4.2", "4.3", "4.4", "4.5", "6.1"] },
    { "id": 3, "tasks": ["6.2", "6.3", "6.4", "7.1"] },
    { "id": 4, "tasks": ["7.2", "7.3", "7.4", "7.5", "7.6", "9.1"] },
    { "id": 5, "tasks": ["9.2", "9.3", "9.4", "9.5", "9.6"] },
    { "id": 6, "tasks": ["10.1"] }
  ]
}
```
