# SSH 接続ユーザー名記録 設計書

## Overview

2.01-fix-ssh-connection-not-recorded によって、パスワード認証試行を伴わない SSH 接続（ポートスキャン、バナー/バージョン取得のみ、公開鍵認証のみ、`Password:` プロンプトで切断する接続等）が `event_type="ssh_connection"` の `AttackEvent` として `connection_lost` で記録されるようになった。しかし現状の `ssh_connection` イベントには、クライアントが認証開始時に送信したユーザー名（`ssh admin@host` の `admin` 等）が含まれていない。

SSH プロトコルでは、クライアントは認証開始時にユーザー名を送信し、これは `asyncssh.SSHServer.begin_auth(self, username)` の引数で受け取れる。現在の `SSHHoneypotServer.begin_auth` はこの `username` を引数で受け取っているが、保存せずに破棄している。そのため、パスワードを送らずに切断した接続では、攻撃者が狙ったユーザー名（`root`、`admin` 等）が観測できていない。

本 feature の方針は、`begin_auth` で受け取ったユーザー名を `SSHHoneypotServer` のインスタンス属性に保存し、`connection_lost` で `ssh_connection` イベントを構築する際に `raw_data` へ含めることである。この際、既存の分類ロジック（`detection/classifier.py`）を 1 行も変更せずに誤判定を回避するため、格納キー名を `"username"` ではなく **`"connection_username"`** とする（後述の「分類器の誤判定回避」を参照）。認証段階まで到達した接続の `ssh_login_attempt` 記録挙動は一切変更しない。

変更は `src/honeywatch/honeypot/ssh.py` の 1 ファイルに限定し、DB マイグレーション不要・HTTP Honeypot 無変更・新依存なしとする。2.01 で導入した同期→async ブリッジおよび二重記録防止の仕組みはそのまま維持する。

## Glossary

- **SSH_Honeypot_Server**: `src/honeywatch/honeypot/ssh.py` の `SSHHoneypotServer` クラス。接続ごとにインスタンス化される asyncssh 用の SSH サーバーハンドラー。本 feature の唯一の変更対象。
- **接続ユーザー名 (connection_username)**: SSH クライアントが認証開始時に送信するユーザー名。`begin_auth(self, username)` の `username` 引数で受け取る値。`ssh_connection` の `raw_data` には `"connection_username"` キーで格納する。
- **ssh_connection イベント**: パスワード認証試行が 0 回のまま切断された SSH 接続について `connection_lost` で発行される `event_type="ssh_connection"` の `AttackEvent`。2.01 で追加された。
- **ssh_login_attempt イベント**: パスワード認証試行時（`validate_password` 呼び出し時）に発行される `event_type="ssh_login_attempt"` の `AttackEvent`。既存挙動。
- **raw_data**: `AttackEvent` の JSON シリアライズ可能なプロトコル固有データ辞書。DB では JSON カラムに保存される。
- **begin_auth**: `asyncssh.SSHServer` のコールバック。クライアントが認証を開始する際にユーザー名を引数として呼ばれる。asyncssh の内部実装により複数回呼ばれ得る。
- **connection_lost**: `asyncssh.SSHServer` の同期コールバック。接続切断時にイベントループ内から呼ばれる。
- **_is_credential_attack**: `src/honeywatch/detection/classifier.py` の判定メソッド。`raw_data.get("username")` / `raw_data.get("password")` を既知の弱い認証情報リストと照合する。本 feature では変更しない。

## Architecture

本変更はアーキテクチャ全体（Honeypot → Collector → Detection → Database）に影響を与えない。変更は Honeypot 層の `SSHHoneypotServer` 内に閉じており、既存のイベント発行経路（`emit_event` → `EventQueue`）や Detection 層のインターフェースは不変である。

```
SSH クライアント
   │ begin_auth(username)         ← 【変更】username を self._username へ保存
   │ (認証試行なしで切断)
   ▼
SSHHoneypotServer.connection_lost  ← 【変更】raw_data に connection_username を付与
   │ AttackEvent(event_type="ssh_connection")
   ▼
emit_event → EventQueue → ...（以降 無変更）
   │
   ▼
detection/classifier.py            ← 【無変更】raw_data.get("username") は None を返し素通り
```

### 変更対象メソッド

| メソッド | 変更内容 |
|---------|---------|
| `SSHHoneypotServer.__init__` | 接続ユーザー名保持属性 `self._username: str = ""` を追加 |
| `SSHHoneypotServer.begin_auth` | 受け取った `username` を `self._username` に保存してから既存どおり `return True` |
| `SSHHoneypotServer.connection_lost` | `ssh_connection` の `raw_data` に `"connection_username": self._username` を追加 |

### 無変更のメソッド・コンポーネント

`validate_password`（`ssh_login_attempt` 側）、`connection_made`、`password_auth_supported`、`SSHHoneypot`（親クラス）、`SSHEventData`、`AttackEvent`、`detection/classifier.py`、HTTP Honeypot、DB モデル、マイグレーション。

## Components and Interfaces

### `SSHHoneypotServer.__init__`（属性追加）

既存の初期化に加え、接続ユーザー名を保持する属性を初期値 空文字で追加する（Requirement 1.3）。空文字を初期値とすることで、`begin_auth` が一度も呼ばれずに切断された接続でも `connection_username: ""` として一貫した型（`str`）でイベントを発行できる。

```python
def __init__(self, honeypot: "SSHHoneypot") -> None:
    self._honeypot = honeypot
    self._attempts = 0
    self._conn_start = time.time()
    self._peer_addr: tuple[str, int] | None = None
    self._client_version = ""
    self._conn: asyncssh.SSHServerConnection | None = None
    self._pending_tasks: set[asyncio.Task[None]] = set()
    # 接続ユーザー名。begin_auth で受け取り保存する。
    # begin_auth が呼ばれない接続（純粋なポートスキャン・バナー取得のみ）では
    # 空文字のまま connection_lost に到達する（Requirement 1.3 / 2.3）。
    self._username: str = ""
```

### `SSHHoneypotServer.begin_auth`（ユーザー名保存）

`begin_auth` で受け取った `username` を `self._username` に保存してから、既存どおり `return True` する（Requirement 1.1 / 1.2）。既存のシグネチャ（`begin_auth(self, username: str) -> bool`）および戻り値（`True`）は変更しない。

```python
def begin_auth(self, username: str) -> bool:
    """認証を開始する（常に認証を要求する）.

    クライアントが送信した接続ユーザー名を保存する。パスワードを
    送らずに切断された接続でも、標的とされたユーザー名を観測できるようにする。

    Args:
        username: クライアントが送信したユーザー名

    Returns:
        True: 認証が必要（既存挙動を維持）
    """
    # 接続ユーザー名を保存する。asyncssh の内部実装により begin_auth は
    # 同一接続で複数回呼ばれ得るため、最後に受け取った値で上書きする。
    self._username = username
    return True
```

#### 複数回呼び出し時の扱い（最後の値を保持）

asyncssh では、クライアントが複数の認証方式を順に試みる過程で `begin_auth` が同一接続に対して複数回呼ばれ得る。本設計では **最後に受け取った値を保持**する（単純な代入による上書き）方針を採る。理由は以下のとおり。

- ユーザー名は通常 1 接続で一定であり、複数回呼ばれても同じ値であることが多い。最後の値・最初の値のいずれでも実用上の差はほぼない。
- 最後の値を保持する実装は単純な代入のみで済み、「初回のみ保存する」条件分岐（空判定など）を追加しないため、コードが最小かつ意図が明快である。
- 万一クライアントが方式ごとに異なるユーザー名を送るケースでも、切断直前に最後に提示されたユーザー名を記録する挙動は観測データとして自然である。

### `SSHHoneypotServer.connection_lost`（raw_data へのユーザー名付与）

2.01 で追加した `ssh_connection` 発行処理の `raw_data` に、接続ユーザー名を `"connection_username"` キーで追加する（Requirement 2.1 / 2.2 / 2.3）。既存フィールド（`client_version` / `connection_duration` / `auth_attempts`）は従来どおり維持する（Requirement 2.4）。二重記録防止（`self._attempts == 0` のときのみ発行）および同期→async ブリッジ（`asyncio.create_task` + `_pending_tasks`、`RuntimeError` フォールバック）は 2.01 のまま変更しない。

変更箇所は `raw_data` の組み立て部分のみ:

```python
raw_data: dict[str, object] = {
    # 接続段階では SSH バージョン交換が未完了で空になり得るが、
    # 空でもイベント発行は妨げない（既存挙動）。
    "client_version": self._client_version,
    # 接続確立から切断までの経過時間（秒、0 以上）。
    "connection_duration": time.time() - self._conn_start,
    # バグ条件により認証試行は常に 0。
    "auth_attempts": 0,
    # 接続ユーザー名。begin_auth で保存した値。取得できなかった場合は
    # 初期値の空文字となる（Requirement 2.3）。
    # キー名を "username" ではなく "connection_username" とする理由は
    # 「分類器の誤判定回避」を参照。
    "connection_username": self._username,
}
```

`self._username` は `begin_auth` が呼ばれていれば当該ユーザー名、呼ばれていなければ初期値の空文字となる。いずれの場合も `str` 型が保証されるため、イベント発行を妨げない（Requirement 2.3）。

## 分類器の誤判定回避（重要な設計判断）

本 feature の中核となる設計判断である。**分類器 `detection/classifier.py` は本 feature で一切変更しない**という制約のもとで、接続ユーザー名の追加が既存分類を壊さないようにキー名を選定する。

### 問題

`detection/classifier.py` の `_is_credential_attack` は、`raw_data` のユーザー名/パスワードを既知の弱い認証情報リストと照合し、いずれかが一致すると `credential_attack` と判定する。該当ロジックは以下のとおり（引用）:

```python
def _is_credential_attack(self, event: AttackEvent) -> bool:
    """既知の弱いユーザー名/パスワードによる攻撃か判定する."""
    if event.protocol != "ssh":
        return False

    rule = self._rules.attack_types.credential_attack
    username = event.raw_data.get("username")
    password = event.raw_data.get("password")

    username_match = isinstance(username, str) and username in rule.usernames
    password_match = isinstance(password, str) and password in rule.passwords

    return username_match or password_match
```

ここで、`ssh_connection` の `raw_data` に接続ユーザー名を `"username"` というキーで格納すると、`event.raw_data.get("username")` が当該ユーザー名（例: `root`、`admin`）を返す。これらは `rule.usernames`（既知の弱いユーザー名リスト）に含まれ得るため、`username_match` が `True` となり、**パスワードを一切送信していない単なる接続（ポートスキャン等）が誤って `credential_attack` に分類される**。これは観測の意味を歪め、`ssh_connection`（接続そのものの観測）と `ssh_login_attempt`（実際の認証試行）の区別を崩す。

### 解決策: キー名を `connection_username` にする

`raw_data` の格納キー名を `"username"` ではなく **`"connection_username"`** とする。これにより:

- `_is_credential_attack` 内の `event.raw_data.get("username")` は、`ssh_connection` の `raw_data` に `"username"` キーが存在しないため **`None` を返す**。
- `isinstance(None, str)` は `False` となり、`username_match` は必ず `False` になる。
- `ssh_connection` は `password` キーも持たないため `password_match` も `False`。
- 結果として `_is_credential_attack` は `False`（素通り）を返し、`ssh_connection` は `credential_attack` に分類されない。

この方針により、**分類器を 1 行も変更せずに誤判定を回避**できる。分類器は自身のロジック（`"username"` キーを参照）のまま、`ssh_connection` を素通りさせる。接続ユーザー名は `"connection_username"` キーとして観測データに保存されるため、ダッシュボードや将来の分析では別途参照できる（Requirement 3.3）。

なお 2.01 の `ssh_connection` は `password` キーも持たない設計であり、本 feature でも `password` キーは追加しない。したがって `password_match` 経路でも誤判定は発生しない。

## Data Models

`AttackEvent` および `SSHEventData` の定義は変更しない。`ssh_connection` の `raw_data` は 2.01 と同じ dict 直接構築（案B）を踏襲し、キーを 1 つ追加するのみである。

### `ssh_connection` の `raw_data` スキーマ（本 feature 適用後）

| キー | 型 | 説明 |
|------|----|------|
| `client_version` | `str` | SSH クライアントバージョン（接続段階では空になり得る） |
| `connection_duration` | `float` | 接続確立から切断までの経過秒数（0 以上） |
| `auth_attempts` | `int` | 認証試行回数（`ssh_connection` では常に 0） |
| `connection_username` | `str` | 【追加】接続ユーザー名。未取得時は空文字 |

`ssh_login_attempt` 側の `raw_data`（`SSHEventData.model_dump()` 由来の `username` / `password` / `client_version` / `connection_duration` / `auth_success`）は無変更（Requirement 3.1）。

## Error Handling

本 feature はエラーハンドリング経路を新規に追加しない。関連する既存挙動をそのまま維持する。

- **接続ユーザー名の未取得**: `begin_auth` が呼ばれずに切断された接続では `self._username` が初期値の空文字のままとなる。この場合も `connection_username: ""` としてイベントを発行し、発行自体は妨げない（Requirement 2.3）。例外は発生しない。
- **同期→async ブリッジのフォールバック**: 2.01 のとおり、`connection_lost` で実行中イベントループが取得できない場合（`RuntimeError`）はイベント発行を諦め `logger.warning` のみとし、`connection_lost` から例外を伝播させない。本 feature はこの挙動を変更しない。
- **二重記録防止**: `self._attempts != 0` の場合は 2.01 のとおり早期 return し、`ssh_connection` を発行しない。本 feature はこの挙動を変更しない（Requirement 3.2）。

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

前段の prework 分析に基づき、テスト可能な受け入れ基準を 3 つの property に集約した。round-trip 系（1.1 / 2.1 / 2.2）および既存フィールド維持（2.4）は Property 1 に統合し、認証試行あり接続の preservation（3.1 / 3.2）は Property 2 に統合し、誤判定回避（3.3）は独立した価値を持つため Property 3 とした。1.2 / 1.3 / 2.3 / 3.4 は EXAMPLE / EDGE_CASE / SMOKE としてユニットテストまたはレビューに委ねる。

### Property 1: 接続ユーザー名の round-trip と既存フィールドの維持

*For any* 接続ユーザー名文字列 `u` について、`begin_auth(u)` を呼んだ後にパスワード認証試行なし（`self._attempts == 0`）で切断された SSH 接続が発行する `ssh_connection` イベントは、`raw_data["connection_username"] == u` を満たし、かつ `raw_data` に既存フィールド `client_version`（`str`）・`connection_duration`（`float`, 0 以上）・`auth_attempts`（`0`）をすべて含む。

**Validates: Requirements 1.1, 2.1, 2.2, 2.4**

### Property 2: 認証試行あり接続の preservation（排他性）

*For any* ユーザー名/パスワードの組でパスワード認証が試行された（`validate_password` が 1 回以上呼ばれ `self._attempts >= 1` となった）SSH 接続について、切断時に発行されるイベントは `event_type="ssh_login_attempt"` のみであり、`ssh_connection` は発行されず、その `raw_data` は `username` / `password` / `client_version` / `connection_duration` / `auth_success` の構造を維持する。

**Validates: Requirements 3.1, 3.2**

### Property 3: 分類器の誤判定回避

*For any* 接続ユーザー名文字列 `u`（既知の弱いユーザー名 `root`・`admin` 等を含む）について、当該 `u` を持つ `ssh_connection` イベントの `raw_data` には `"username"` キーが存在せず（`"connection_username"` キーで保持され）、これを分類器に通しても `_is_credential_attack` が `False` を返し `credential_attack` と判定されない。

**Validates: Requirements 3.3**

## Testing Strategy

### 方針

2.01 とテスト方針を揃える。hypothesis は導入せず、`@pytest.mark.parametrize` で複数ケースを列挙して property を近似的に検証する。テスト実行は `uv run` を使わずプレーンな `pytest` を用いる。テストは `tests/test_honeypot/` に配置し、イベント発行の検証は `emit_event` または `EventQueue.publish` をモックして呼び出し内容を捕捉する。新規依存は追加しない。

### Property Tests（parametrize による近似）

各 property テストは対応する design 上の property を参照する。

- **Feature: 2.02-feat-ssh-connection-username, Property 1: 接続ユーザー名の round-trip と既存フィールドの維持**
  - `@pytest.mark.parametrize` で複数の username（`root`、`admin`、`""`（空文字）、マルチバイト文字、記号・空白を含む文字列、長い文字列等）を列挙する。
  - 各ケースで `begin_auth(u)` → 認証試行なしで `connection_lost` を実行し、発行された `ssh_connection` の `raw_data["connection_username"] == u` を検証する。
  - 併せて `raw_data` に `client_version`・`connection_duration`（0 以上）・`auth_attempts == 0` が含まれることを検証する。

- **Feature: 2.02-feat-ssh-connection-username, Property 2: 認証試行あり接続の preservation（排他性）**
  - `@pytest.mark.parametrize` で複数の username/password の組を列挙する。
  - 各ケースで `validate_password` を 1 回以上呼んだ後 `connection_lost` を呼び、`ssh_login_attempt` が発行され、`ssh_connection` が発行されないことを検証する。
  - 発行された `ssh_login_attempt` の `raw_data` が `username` / `password` / `client_version` / `connection_duration` / `auth_success` を持つことを検証する。

- **Feature: 2.02-feat-ssh-connection-username, Property 3: 分類器の誤判定回避**
  - `@pytest.mark.parametrize` で既知の弱いユーザー名を含む複数の username を列挙する。
  - 各ケースで生成した `ssh_connection` イベントの `raw_data` に `"username"` キーが存在せず `"connection_username"` キーが存在することを検証する。
  - 当該イベントを `AttackClassifier`（またはその `_is_credential_attack`）に通し、`credential_attack` と判定されないことを検証する。

### Unit Tests（EXAMPLE / EDGE_CASE）

- **begin_auth 戻り値（1.2, EXAMPLE）**: 数個の username で `begin_auth` を呼び、戻り値が `True` であることを検証する。
- **初期値（1.3, EXAMPLE）**: インスタンス生成直後に接続ユーザー名が空文字であること、または `begin_auth` 未呼び出しで `connection_lost` した際に `connection_username == ""` となることを検証する。
- **begin_auth 未呼び出し切断（2.3, EDGE_CASE）**: `begin_auth` を呼ばずに（純粋なポートスキャン想定で）`connection_lost` を呼び、`ssh_connection` が 1 件発行され、`connection_username == ""` であり、既存フィールドも従来どおり含まれることを検証する。
- **begin_auth 複数回呼び出し（設計判断の検証）**: `begin_auth` を異なる username で複数回呼んだ後に切断し、`connection_username` が最後に受け取った値になることを検証する。

### スコープ外（SMOKE / レビュー）

- **変更範囲の限定（3.4, SMOKE）**: 変更が `src/honeywatch/honeypot/ssh.py` の 1 ファイルに限定され、新依存が追加されていないことは diff レビューおよび `pyproject.toml` の無変更確認で担保する。自動テスト対象外とする。
