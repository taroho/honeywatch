# Requirements Document

## Introduction

2.01-fix-ssh-connection-not-recorded において、パスワード認証試行を伴わない SSH 接続（ポートスキャン、バナー取得のみ、公開鍵認証のみ、`Password:` プロンプトで切断する接続など）を `event_type="ssh_connection"` の `AttackEvent` として記録する仕組みを追加した。しかし現状の `ssh_connection` イベントには、接続時にクライアントが送信したユーザー名（`ssh admin@host` の `admin` など）が含まれていない。

SSH プロトコルでは、クライアントは認証開始時にユーザー名を送信し、これは `asyncssh.SSHServer.begin_auth(self, username)` の引数として受け取れる。現在の `SSHHoneypotServer.begin_auth` はこの `username` を引数で受け取っているが、保存せずに破棄している。そのため、パスワードを送らずに切断した接続では、攻撃者が狙ったユーザー名（`root`、`admin` など）が観測できていない。

本 feature では、`begin_auth` で受け取ったユーザー名を保存し、`connection_lost` で `ssh_connection` イベントを生成する際に `raw_data` へ含めることで、観測データを拡充する。認証段階まで到達した接続の `ssh_login_attempt` 記録挙動は変更しない。

## Glossary

- **SSH_Honeypot_Server**: `src/honeywatch/honeypot/ssh.py` の `SSHHoneypotServer` クラス。接続ごとにインスタンス化される asyncssh 用の SSH サーバーハンドラー。本 feature の変更対象。
- **ssh_connection イベント**: パスワード認証試行が 0 回のまま切断された SSH 接続について、`connection_lost` で発行される `event_type="ssh_connection"` の `AttackEvent`。2.01-fix-ssh-connection-not-recorded で追加された。
- **ssh_login_attempt イベント**: パスワード認証試行時（`validate_password` 呼び出し時）に発行される `event_type="ssh_login_attempt"` の `AttackEvent`。既存挙動。
- **接続ユーザー名 (connection_username)**: SSH クライアントが認証開始時に送信するユーザー名。`begin_auth(self, username)` の `username` 引数で受け取る値。
- **raw_data**: `AttackEvent` の JSON シリアライズ可能なプロトコル固有データ辞書。DB では JSON カラムに保存される。
- **begin_auth**: `asyncssh.SSHServer` のコールバック。クライアントが認証を開始する際にユーザー名を引数として呼ばれる。
- **connection_lost**: `asyncssh.SSHServer` のコールバック。接続が切断された際に呼ばれる同期コールバック。

## Requirements

### Requirement 1: 接続ユーザー名の保存

**User Story:** セキュリティアナリストとして、パスワードを送らずに切断した SSH 接続についても攻撃者が狙ったユーザー名を知りたい。そうすれば、認証前切断であっても標的とされたアカウント（root, admin 等）を把握できる。

#### Acceptance Criteria

1. WHEN SSH クライアントが認証を開始し `begin_auth` がユーザー名を伴って呼ばれる, THE SSH_Honeypot_Server SHALL 当該ユーザー名をインスタンス属性として保存する。
2. WHEN `begin_auth` が呼ばれる, THE SSH_Honeypot_Server SHALL 認証を要求する既存の戻り値（True）を維持する。
3. THE SSH_Honeypot_Server SHALL 接続ユーザー名の初期値として空文字を保持する。

### Requirement 2: ssh_connection イベントへのユーザー名付与

**User Story:** セキュリティアナリストとして、`ssh_connection` イベントに接続ユーザー名を含めてほしい。そうすれば、認証前切断の観測データからも標的ユーザー名を分析できる。

#### Acceptance Criteria

1. WHEN パスワード認証試行が 0 回のまま切断された接続について `connection_lost` が `ssh_connection` イベントを生成する, THE SSH_Honeypot_Server SHALL 保存済みの接続ユーザー名を当該イベントの `raw_data` に含める。
2. WHERE 接続ユーザー名を取得できた, THE SSH_Honeypot_Server SHALL 当該ユーザー名の文字列値を `raw_data` に格納する。
3. IF 接続ユーザー名を取得できなかった（`begin_auth` が呼ばれずに切断された）, THEN THE SSH_Honeypot_Server SHALL 空文字を接続ユーザー名として `raw_data` に格納し、イベント発行を継続する。
4. WHEN `ssh_connection` イベントを生成する, THE SSH_Honeypot_Server SHALL 既存の `raw_data` フィールド（`client_version`、`connection_duration`、`auth_attempts`）を従来どおり含める。

### Requirement 3: 既存挙動の維持（regression 防止）

**User Story:** 運用者として、本変更が既存の記録挙動に影響しないことを保証してほしい。そうすれば、既存の分析・集計が破綻しない。

#### Acceptance Criteria

1. WHEN SSH クライアントがパスワード認証を試行する（`validate_password` が呼ばれる）, THE SSH_Honeypot_Server SHALL `event_type="ssh_login_attempt"` の `AttackEvent` を従来どおり記録し、`SSHEventData` の構造（`username`/`password`/`client_version`/`connection_duration`/`auth_success`）を維持する。
2. WHEN パスワード認証試行が 1 回以上あった接続が切断される, THE SSH_Honeypot_Server SHALL `ssh_connection` イベントを発行しない既存の二重記録防止挙動を維持する。
3. WHEN 接続ユーザー名を `ssh_connection` の `raw_data` に格納する, THE SSH_Honeypot_Server SHALL 接続ユーザー名を `username` 以外のキー名で格納し、既存の分類ロジック（`detection/classifier.py`）が `raw_data.get("username")` を参照する挙動を変更しない。
4. THE SSH_Honeypot_Server SHALL 本 feature の変更を `src/honeywatch/honeypot/ssh.py` の 1 ファイルに限定し、新たな依存関係を追加しない。
