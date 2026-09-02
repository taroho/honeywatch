# SSH Connection Not Recorded Bugfix Design

## Overview

SSH Honeypot（`src/honeywatch/honeypot/ssh.py`）は現状、パスワード認証試行（`validate_password` が呼ばれるケース）が発生したときにのみ `AttackEvent`（`event_type="ssh_login_attempt"`）を発行している。接続確立・切断コールバック（`connection_made` / `connection_lost`）は `logger.debug` によるログ出力のみで、イベントを一切発行しない。そのため、パスワード認証まで到達しない接続（ポートスキャン、バナー/バージョン取得のみ、公開鍵認証のみ、認証方式確認のみ等）が DB に記録されず、観測データが取りこぼされている。

本バグ修正の方針は、**認証試行が 0 回だった接続に限り**、切断時（`connection_lost`）に `event_type="ssh_connection"` の `AttackEvent` を 1 件発行することである。認証試行が 1 回以上あった接続は既に `ssh_login_attempt` として記録済みのため、`ssh_connection` を発行せず二重記録を防ぐ。これにより既存の `ssh_login_attempt` 記録挙動および HTTP Honeypot の挙動は一切変更しない（regression 防止）。

修正は `connection_lost` への発行処理追加が中心で、既存メソッドのシグネチャや `validate_password` の挙動は変更しない、最小限の変更に留める。

## Glossary

- **Bug_Condition (C)**: バグを引き起こす入力条件。SSH 接続でパスワード認証試行が 0 回のまま切断されたケース（`protocol == "ssh"` かつ `password_auth_attempts == 0`）。
- **Property (P)**: バグ条件を満たす入力に対する期待挙動。当該接続について `event_type="ssh_connection"` の `AttackEvent` が 1 件発行されること。
- **Preservation**: 修正によって変えてはならない既存挙動。認証試行あり接続の `ssh_login_attempt` 記録、`validate_password` の認証拒否・最大試行回数切断、HTTP Honeypot の `http_request` 記録、既存 `event_type` に対する分類結果。
- **F**: 修正前の SSH Honeypot（認証試行時のみイベント発行）。
- **F'**: 修正後の SSH Honeypot（認証試行なし接続もイベント発行）。
- **`SSHHoneypotServer`**: `src/honeywatch/honeypot/ssh.py` の `asyncssh.SSHServer` サブクラス。接続ごとにインスタンス化され、コールバック（`connection_made` / `connection_lost` / `validate_password`）を受け取る。
- **`connection_lost`**: `src/honeywatch/honeypot/ssh.py` の同期コールバック。接続切断時に asyncssh のイベントループ内から呼ばれる。
- **`emit_event`**: `src/honeywatch/honeypot/base.py` の `BaseHoneypot.emit_event`。**async** メソッドで、内部で `EventQueue.publish` を await し、Redis 断時は `deque(maxlen=10000)` バッファへ退避する。同期版のイベント投入口は存在しない。
- **`self._attempts`**: `SSHHoneypotServer` が保持するパスワード認証試行回数カウンタ。`validate_password` 内で `+= 1` される。切断時に参照可能で、`password_auth_attempts` の実体として扱う。

## Bug Details

### Bug Condition

このバグは、SSH クライアントが接続を確立した後、**パスワード認証を一度も試行せずに切断した**場合に顕在化する。`connection_made` / `connection_lost` は `logger.debug` のみを行い `emit_event` を呼ばないため、`validate_password` が呼ばれない接続はイベントとして記録されない。切断時点で `self._attempts == 0` であることが、この「認証試行なし接続」を識別する指標となる。

**Formal Specification:**
```
FUNCTION isBugCondition(input)
  INPUT: input of type SSHConnection
  OUTPUT: boolean

  // パスワード認証試行が 0 回のまま切断された SSH 接続を
  // 「バグを引き起こす入力」とみなす。
  // （ポートスキャン、バナー/バージョン取得のみ、公開鍵認証のみ、
  //   認証方式確認のみ等が該当。切断時 self._attempts == 0）
  RETURN input.protocol == "ssh"
         AND input.password_auth_attempts == 0
END FUNCTION
```

### Examples

- SSH ポートへ TCP 接続し、SSH バージョン交換直後に切断（`nc` やスキャナによるバナー取得）
  - 期待: `event_type="ssh_connection"` が 1 件記録される
  - 実際（修正前）: `AttackEvent` が 0 件（`connection_lost` は debug ログのみ）
- SSH ボットが公開鍵認証のみを試行して拒否・切断（`validate_password` が呼ばれない）
  - 期待: `event_type="ssh_connection"` が 1 件記録される
  - 実際（修正前）: `AttackEvent` が 0 件
- SSH クライアントが `root`/`123456` でパスワード認証を試行して切断（`self._attempts == 1`）
  - 期待: 従来どおり `ssh_login_attempt` が記録され、`ssh_connection` は発行されない
  - 実際（修正前）: `ssh_login_attempt` が記録される（これは正しい挙動、変更しない）
- エッジケース: 接続直後に例外（`exc is not None`）で切断され、かつ `self._attempts == 0` の場合
  - 期待: `ssh_connection` を 1 件記録する（取得できた範囲の情報で発行する）

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- パスワード認証試行あり接続（`self._attempts >= 1`）では、従来どおり `event_type="ssh_login_attempt"` の `AttackEvent` が記録され、`ssh_connection` は発行されない（二重記録防止）。
- `validate_password` は常に `False` を返し、`settings.honeypot.ssh_max_auth_attempts` 到達で切断ログを出す既存挙動を維持する。
- `validate_password` 内で `self._conn.get_extra_info("client_version", ...)` により `client_version` を取り直す挙動を維持する。
- `SSHEventData` の構造（`username` / `password` / `client_version` / `connection_duration` / `auth_success`）を維持する。
- HTTP Honeypot（`src/honeywatch/honeypot/http.py`）の `http_request` 等の記録挙動は一切変更しない。
- 既存 `event_type`（`ssh_login_attempt` / `http_request` 等）に対する分類結果（`attack_type` / `severity`）を維持する。

**Scope:**
バグ条件を満たさない入力（`self._attempts >= 1` の SSH 接続、および全 HTTP 接続）は、本修正の影響を一切受けない。具体的には以下が対象外である:
- パスワード認証試行を伴う SSH 接続
- HTTP リクエスト全般
- 既存分類ロジックの既存 `event_type` に対する挙動

**Note:** バグ条件を満たす入力に対する期待挙動（`ssh_connection` の 1 件発行）は Correctness Properties の Property 1 に定義する。本セクションは「変えてはならないもの」に焦点を当てる。

## Hypothesized Root Cause

バグ記述と実装確認の結果、根本原因は以下の構造的欠陥である。

1. **記録が `validate_password` 依存になっている構造的欠陥**: SSH 接続の観測イベント発行が `validate_password`（パスワード認証試行時のみ呼ばれる async メソッド）にのみ実装されている。`connection_made` / `connection_lost` は `logger.debug` のみで `emit_event` を呼ばない。このため、パスワード認証まで到達しない接続はイベント発行の経路を一切持たない。

2. **接続ライフサイクルのイベント欠落**: `connection_lost` は切断時に `self._attempts` を参照できる位置にありながら、記録処理を持たない。接続そのものを表すイベント種別（`ssh_connection`）が存在しない。

3. **同期コールバックと async 発行口の非整合**: `connection_lost` は同期メソッドだが、唯一のイベント投入口 `emit_event` は async である。同期コンテキストから async 発行を行う仕組みが実装されていないため、仮に発行を追加しようとしても直接 await できない（修正時に対処が必要な設計上の制約）。

## Correctness Properties

Property 1: Bug Condition - 認証試行なし接続の記録

_For any_ 入力でバグ条件が成立する場合（`isBugCondition` が true、すなわち `protocol == "ssh"` かつ切断時 `self._attempts == 0`）、修正後の F' は当該接続について `event_type="ssh_connection"` の `AttackEvent` を**ちょうど 1 件**発行し、そのイベントは `source_ip == 接続元 IP`、`protocol == "ssh"`、`destination_port == 記録用宛先ポート` を満たし、`raw_data` に `client_version`・`connection_duration`（0 以上）・`auth_attempts == 0` を含む。

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation - 認証試行あり接続および HTTP の不変性

_For any_ 入力でバグ条件が成立しない場合（`isBugCondition` が false、すなわち `self._attempts >= 1` の SSH 接続、または全 HTTP 接続）、修正後の F' は修正前の F と同一のイベント（`ssh_login_attempt` / `http_request` 等）を発行し、`ssh_connection` は発行しない。これにより既存の認証試行記録・HTTP 記録・既存 `event_type` の分類結果が保存される。

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**

## Fix Implementation

### Changes Required

根本原因分析が正しいと仮定した場合の変更内容。

**File**: `src/honeywatch/honeypot/ssh.py`

**Function**: `SSHHoneypotServer.connection_lost`（および `__init__` への状態追加）

**Specific Changes**:

1. **`connection_lost` での条件付きイベント発行**:
   - 切断時に `self._attempts == 0` の場合**のみ**、`event_type="ssh_connection"` の `AttackEvent` を 1 件構築して発行する。
   - `self._attempts >= 1` の場合は既に `ssh_login_attempt` を記録済みのため、`ssh_connection` を発行しない（二重記録防止、Preservation 3.1 の担保）。

2. **同期→async 発行のブリッジ（`asyncio.create_task`）**:
   - `connection_lost` は同期メソッド、`emit_event` は async。`asyncio.create_task(self._honeypot.emit_event(event))` でイベントループへスケジュールする。asyncssh のコールバックはイベントループ内から呼ばれるため、実行中ループが存在する前提とする。
   - 作成した Task の参照を `SSHHoneypotServer` の集合（例: `self._pending_tasks: set[asyncio.Task[None]]`）に保持し、Task が完了するまで GC されないようにする。`task.add_done_callback(self._pending_tasks.discard)` で完了後に集合から除去する。
   - フォールバック: `asyncio.get_running_loop()` が `RuntimeError` を送出する（実行中ループが取得できない）場合は、イベント発行を諦めて `logger.warning` を出すのみとし、`connection_lost` から例外を伝播させない。

3. **データ構造の判断（`raw_data` を dict で直接構築 = 案B を採用）**:
   - `ssh_connection` は認証情報（`username` / `password`）を持たない接続イベントである。`SSHEventData` は `username`・`password` が必須フィールドであり、これらを空文字で埋める（案A）と、認証情報を持たない接続に空の認証フィールドを付与することになり意味的に不正確である。加えて product.md の「機密性の高い値は必要以上に保存しない」方針に反する。
   - したがって案B を採用し、`raw_data` に接続イベント専用フィールドのみを直接 dict で構築する:
     - `client_version`: 取得できた範囲の値（接続段階では空になり得る。空でも発行を妨げない、Requirement 2.3）
     - `connection_duration`: `time.time() - self._conn_start`（0 以上）
     - `auth_attempts`: `0`（バグ条件により常に 0）
   - 分類への影響: `classifier._is_credential_attack` は `raw_data` の `username` / `password` を参照するが、`ssh_connection` の `raw_data` にこれらが存在しなければ `.get()` が `None` を返して `isinstance(..., str)` が False となり素通りする。よって既存分類を壊さない（Preservation 3.5 の担保）。この理由により案B は分類ロジックとも整合する。

4. **イベント構築時の値の取得元**:
   - `source_ip` = `self._peer_addr[0]`（未取得時は `"0.0.0.0"`、`validate_password` の既存フォールバックと揃える）
   - `source_port` = `self._peer_addr[1]`（未取得時は `0`）
   - `destination_port` = `self._honeypot.port`（= `ssh_reported_port`、既存と同一）
   - `protocol` = `"ssh"`

5. **状態の追加**:
   - `SSHHoneypotServer.__init__` に `self._pending_tasks: set[asyncio.Task[None]] = set()` を追加する。既存フィールド（`self._attempts`・`self._conn_start`・`self._peer_addr`・`self._client_version`・`self._conn`）はそのまま利用する。

**変更しないもの**: `validate_password`・`connection_made`・`begin_auth`・`password_auth_supported`・`SSHHoneypot`（親クラス）・`SSHEventData`・`AttackEvent`・`classifier`・HTTP Honeypot・DB モデル・マイグレーション。

## Testing Strategy

### Validation Approach

テストは 2 段階で進める。まず修正前コードでバグを再現する反例を surface し、次に修正後コードで Fix Checking（バグ条件下で `ssh_connection` が発行される）と Preservation Checking（バグ条件外で挙動が不変）を検証する。テストは `tests/test_honeypot/` に配置し、pytest + pytest-asyncio を用いる（新規依存は追加しない）。イベント発行の検証は `emit_event` または `EventQueue.publish` をモックして呼び出し内容を捕捉する。

### Exploratory Bug Condition Checking

**Goal**: 修正実装前に、バグを再現する反例を surface し、根本原因分析（記録が `validate_password` 依存であること）を確認する。反証された場合は再仮説を立てる。

**Test Plan**: `SSHHoneypotServer` に対し、`connection_made` → `connection_lost`（`validate_password` を呼ばない）というシーケンスを実行し、`emit_event` が呼ばれないことを観察する。修正前コードで実行して失敗（イベント 0 件）を確認する。

**Test Cases**:
1. **Banner Grab Test**: `connection_made` 後、認証試行なしで `connection_lost` を呼ぶ。`ssh_connection` イベントが発行されることを期待（修正前は 0 件で fail）。
2. **Public Key Only Test**: `validate_password` を呼ばず切断するシナリオを `self._attempts == 0` で表現。`ssh_connection` 発行を期待（修正前は fail）。
3. **Connection With Exception Test**: `connection_lost(exc=SomeError())` かつ `self._attempts == 0`。`ssh_connection` 発行を期待（修正前は fail）。

**Expected Counterexamples**:
- 認証試行なし切断で `emit_event` が一度も呼ばれない。
- 想定原因: `connection_lost` が `logger.debug` のみで発行経路を持たない構造的欠陥。

### Fix Checking

**Goal**: バグ条件を満たす全入力に対し、修正後関数が期待挙動（`ssh_connection` を 1 件発行）を満たすことを検証する。

**Pseudocode:**
```
FOR ALL input WHERE isBugCondition(input) DO
  events := connectionLifecycle_fixed(input)   // 認証試行なしの接続→切断
  ASSERT count(events WHERE event_type == "ssh_connection") == 1
    AND events[0].source_ip == input.source_ip
    AND events[0].protocol == "ssh"
    AND events[0].raw_data["auth_attempts"] == 0
    AND events[0].raw_data["connection_duration"] >= 0
END FOR
```

### Preservation Checking

**Goal**: バグ条件を満たさない全入力に対し、修正後関数が修正前関数と同一の結果を生成することを検証する。

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT connectionLifecycle_original(input) == connectionLifecycle_fixed(input)
END FOR
```

**Testing Approach**: Preservation Checking には property-based testing（hypothesis）を推奨する。入力ドメイン全域で多数のケースを自動生成し、手動ユニットテストが見逃すエッジケースを捕捉し、非バグ入力での挙動不変を強く保証できるためである。

**Test Plan**: 修正前コードで認証試行あり接続・HTTP 接続の挙動を観察し、その挙動を捕捉する property-based テストを書く。

**Test Cases**:
1. **Auth Attempt Preservation**: `validate_password` を 1 回以上呼んだ後に切断した場合、`ssh_login_attempt` が従来どおり記録され、かつ `ssh_connection` が発行されないことを検証（修正前挙動を確認してから固定）。
2. **SSHEventData Structure Preservation**: `ssh_login_attempt` の `raw_data` が `username` / `password` / `client_version` / `connection_duration` / `auth_success` を持つことを検証。
3. **HTTP No Impact**: HTTP Honeypot の `http_request` 記録が本修正の影響を受けないことを検証。

### Unit Tests

- 認証試行なし接続→切断で `ssh_connection` が 1 件発行される（各フィールド検証）。
- 認証試行あり接続→切断で `ssh_connection` が発行されない（`self._attempts >= 1`）。
- 実行中イベントループが取得できないフォールバック時に、例外を伝播させず `logger.warning` のみとなる。
- `client_version` が空文字でもイベント発行が行われる（Requirement 2.3）。

### Property-Based Tests

- `self._attempts` の値域（`0` と `>= 1`）で、発行されるイベント種別が排他になること（`0` → `ssh_connection` のみ、`>= 1` → `ssh_login_attempt` のみ、`ssh_connection` なし）。
- 生成したランダムな接続時間・接続元アドレスに対し、`connection_duration >= 0`・`auth_attempts == 0`・`protocol == "ssh"` の不変条件が保たれること。
- ランダムな `event_type`（`ssh_connection` を含む）を持つ `AttackEvent` を分類器に通しても、`_is_credential_attack` が `username`/`password` 欠如時に素通りし分類が破綻しないこと。

### Integration Tests

- Honeypot 起動から、認証試行なしクライアント接続→切断までの全フローで `ssh_connection` が発行されること。
- 認証試行ありクライアントと認証試行なしクライアントを混在させ、それぞれ正しい `event_type` のみが発行されること。
- 発行された `ssh_connection` イベントが分類・ダッシュボード集計を破綻させないこと（新 `event_type` の増加を破綻なく扱う、Requirement 2.4）。
