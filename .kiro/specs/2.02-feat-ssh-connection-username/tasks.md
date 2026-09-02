# Implementation Plan: SSH 接続ユーザー名記録

## Overview

`src/honeywatch/honeypot/ssh.py` の `SSHHoneypotServer` に接続ユーザー名の保存と `ssh_connection` イベントへの付与を実装する。変更は当該 1 ファイルに閉じ、`__init__`（属性追加）→ `begin_auth`（ユーザー名保存）→ `connection_lost`（`raw_data` へ `connection_username` 付与）の順に段階的に実装する。分類器（`detection/classifier.py`）・HTTP Honeypot・DB モデル・マイグレーション・依存関係は変更しない。

本 feature ではユーザー方針により自動テスト（PBT / pytest）は作成しない。品質確認は静的解析（`ruff check` / `ruff format` / `mypy`）と、Docker 反映後の実接続 + DB 確認で行う。design の Correctness Properties（Property 1〜3）はレビューおよび動作確認で担保する。

## Tasks

- [ ] 1. 接続ユーザー名の保存と ssh_connection への付与を実装する
  - [ ] 1.1 `SSHHoneypotServer.__init__` に接続ユーザー名保持属性を追加する
    - `src/honeywatch/honeypot/ssh.py` の `__init__` 末尾に `self._username: str = ""` を追加する
    - `begin_auth` が一度も呼ばれずに切断された接続でも初期値の空文字を保持できるよう、初期値は空文字（`str`）とする
    - 属性の意図（begin_auth で保存する接続ユーザー名。未取得時は空文字のまま connection_lost に到達する）をコメントで明記する
    - _Requirements: 1.3_
    - _design Property: Property 1（初期値・型保証の前提）, Property 3_

  - [ ] 1.2 `SSHHoneypotServer.begin_auth` で接続ユーザー名を保存する
    - 引数 `username` を `self._username` に代入してから、既存どおり `return True` する
    - asyncssh の仕様上 `begin_auth` は同一接続で複数回呼ばれ得るため、単純代入で「最後に受け取った値」を保持する方針をコメントで明記する
    - シグネチャ（`begin_auth(self, username: str) -> bool`）と戻り値（`True`）は変更しない
    - Google スタイルの docstring に保存目的（パスワード未送信で切断した接続でも標的ユーザー名を観測する）を追記する
    - _Requirements: 1.1, 1.2_
    - _design Property: Property 1_

  - [ ] 1.3 `SSHHoneypotServer.connection_lost` の `ssh_connection` の raw_data にユーザー名を付与する
    - 既存の `raw_data` dict（`client_version` / `connection_duration` / `auth_attempts`）に `"connection_username": self._username` を追加する
    - キー名は `"username"` ではなく `"connection_username"` とする（分類器 `_is_credential_attack` が `raw_data.get("username")` で `None` を得て素通りし、`credential_attack` の誤判定を回避するため）
    - キー名選定理由・既存フィールド維持・二重記録防止（`self._attempts == 0` のときのみ発行）・同期→async ブリッジは 2.01 のまま変更しないことをコメントで明記する
    - `validate_password`（`ssh_login_attempt` 側）は変更しない
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3_
    - _design Property: Property 1, Property 2, Property 3_

- [ ] 2. Checkpoint - 静的解析と変更範囲の確認
  - `ruff check src/honeywatch/honeypot/ssh.py`（またはプロジェクト全体）でリントエラーがないことを確認する
  - `ruff format src/honeywatch/honeypot/ssh.py` を実行しフォーマット差分がないことを確認する
  - `mypy src/honeywatch/honeypot/ssh.py`（または設定に従いプロジェクト全体）で型エラーがないことを確認する
  - 変更が `src/honeywatch/honeypot/ssh.py` の 1 ファイルに限定され、`detection/classifier.py`・HTTP Honeypot・DB モデル・マイグレーションに影響しないこと、`pyproject.toml` に依存追加がないことを diff で確認する
  - エラーや疑問があればユーザーに確認する（`uv run` は使用しない）
  - _Requirements: 3.4_

## 動作確認（コード変更なし・共有タスク）

以下はコード変更を伴わない手動確認手順の共有である。Docker 反映後にユーザー環境で実施する想定であり、コーディングエージェントの実装対象外とする。

- Docker イメージを再ビルドして SSH Honeypot に変更を反映する。
- `ssh admin@<host> -p <port>` 等で接続し、`Password:` プロンプトで `Ctrl+C`（パスワード未送信）して切断する。
- DB の `attack_events` を確認し、当該接続に対応する `event_type="ssh_connection"` のレコードの `raw_data.connection_username` に接続時のユーザー名（例: `admin`）が入っていることを確認する。
- 既存フィールド（`client_version` / `connection_duration` / `auth_attempts`）が従来どおり含まれること、当該接続が `credential_attack` に分類されていないことを併せて確認する（Property 1 / Property 3 の実確認）。
- パスワードを実際に入力した接続では従来どおり `ssh_login_attempt` のみが記録され、`ssh_connection` が発行されないことを確認する（Property 2 の実確認）。

## Notes

- 本 feature は自動テスト（PBT / pytest）を今回は省略する（ユーザー方針）。design の Testing Strategy に記載の property テストは実装しない。
- 品質確認は静的解析（`ruff check` / `ruff format` / `mypy`）と実接続 + DB 確認で担保する。
- 静的解析コマンドは `uv run` を使わずプレーンに記述する。
- 各タスクは requirements の粒度の細かい受け入れ基準と design の Correctness Property を参照している。
- 変更は `ssh.py` 1 ファイルに閉じ、新依存の追加・不要なリファクタリングは行わない。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] }
  ]
}
```
