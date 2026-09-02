# Bugfix Requirements Document

## Introduction

HoneyWatch の SSH Honeypot は、Honeypot に到達した「実際の攻撃・接続」を観測することを目的としている（product.md 参照）。しかし現状の SSH Honeypot 実装（`src/honeywatch/honeypot/ssh.py`）は、パスワード認証試行（`validate_password` が呼ばれるケース）が発生したときのみ `AttackEvent`（`event_type="ssh_login_attempt"`）を発行している。

そのため、パスワード認証まで到達しない接続（ポートスキャン、バナー/バージョン取得のみの接続、公開鍵認証のみを試行して切断するボット、認証方式確認のみの接続など）は一切 DB に記録されず、観測データが取りこぼされている。実際に本番 EC2 で SSH イベントが 0 件のままとなり、「本当に誰も来ていない」のか「認証前接続を取りこぼしている」のかを切り分けられない。

本バグ修正では、認証試行の有無に関わらず SSH 接続そのものを観測イベントとして記録するようにする。一方で、既存の `ssh_login_attempt` の記録挙動、および HTTP Honeypot の挙動は一切変更しない（regression 防止）。

## Bug Analysis

### Current Behavior (Defect)

現状、SSH 接続が確立・切断されても、パスワード認証試行が発生しない限りイベントが記録されない。

1.1 WHEN SSH クライアントが接続を確立した後、パスワード認証を試行せずに切断する（ポートスキャン、バナー/バージョン取得のみ、認証方式確認のみ等）THEN the system は `AttackEvent` を一切発行せず、接続が DB に記録されない（`connection_made` / `connection_lost` は `logger.debug` によるログ出力のみで、`emit_event` を呼ばない）

1.2 WHEN SSH クライアントが公開鍵認証のみを試行して切断する（`validate_password` が呼ばれない）THEN the system は `AttackEvent` を一切発行せず、接続が DB に記録されない

1.3 WHEN 上記 1.1 / 1.2 のような認証前切断が本番環境で多数発生している THEN the system は SSH イベントを 0 件のまま保持し、Port Scan 等の攻撃分類（product.md で分類対象とされている）を行うための観測データが存在しない状態になる

### Expected Behavior (Correct)

認証試行の有無に関わらず、SSH 接続そのものを観測イベントとして 1 件記録する。

2.1 WHEN SSH クライアントが接続を確立した後、パスワード認証を試行せずに切断する THEN the system SHALL 当該接続について `ssh_connection` 相当の `AttackEvent` を 1 件記録する（送信元 IP・送信元ポート・宛先ポート・接続時間などの観測可能な情報を含む）

2.2 WHEN SSH クライアントが公開鍵認証のみを試行して切断する THEN the system SHALL 当該接続について `ssh_connection` 相当の `AttackEvent` を 1 件記録する

2.3 WHEN `ssh_connection` イベントが記録された THEN the system SHALL 接続段階では `client_version` が空になり得ることを許容し、取得できた範囲の情報でイベントを発行する（`client_version` が空でもイベント発行を妨げない）

2.4 WHEN 認証前接続イベント（`ssh_connection`）が記録されるようになった THEN the system SHALL 既存の分類ロジック（`detection`）およびダッシュボード集計が新しい `event_type` の増加を破綻なく扱えるようにする（新 `event_type` により Port Scan 等の分類が可能になる想定を含む）

### Unchanged Behavior (Regression Prevention)

既存の認証試行記録および HTTP Honeypot の挙動は変更しない。

3.1 WHEN SSH クライアントがパスワード認証を試行する（`validate_password` が呼ばれる）THEN the system SHALL CONTINUE TO `event_type="ssh_login_attempt"` の `AttackEvent` を従来どおり記録する（`SSHEventData` の構造・`username`/`password`/`client_version`/`connection_duration`/`auth_success` フィールドを維持）

3.2 WHEN SSH クライアントがパスワード認証を試行する THEN the system SHALL CONTINUE TO 認証を常に失敗させ、最大試行回数超過時に切断する既存の挙動を維持する

3.3 WHEN 認証段階で `client_version` を取り直す（`validate_password` 内で `get_extra_info` により再取得する）THEN the system SHALL CONTINUE TO 当該再取得挙動を維持する

3.4 WHEN HTTP Honeypot（`src/honeywatch/honeypot/http.py`）がリクエストを受信する THEN the system SHALL CONTINUE TO 従来どおり `HTTPEventData` を用いたイベント（`http_request` 等）を記録し、本修正の影響を一切受けない

3.5 WHEN 既存の分類ロジックが `ssh_login_attempt` / `http_request` などの従来の `event_type` を処理する THEN the system SHALL CONTINUE TO 従来どおりの分類結果（`attack_type` / `severity`）を返す

## Bug Condition and Properties

以下は本バグの構造を bug condition methodology で整理したものである。

- **F**: 修正前の SSH Honeypot（認証試行時のみイベント発行）
- **F'**: 修正後の SSH Honeypot（接続そのものもイベント発行）

### Bug Condition Function

```pascal
FUNCTION isBugCondition(X)
  INPUT: X of type SSHConnection
  OUTPUT: boolean

  // パスワード認証試行が発生しなかった SSH 接続を「バグを引き起こす入力」とみなす。
  // （接続確立後、validate_password が一度も呼ばれずに切断されたケース。
  //   ポートスキャン、バナー取得のみ、公開鍵認証のみ、認証方式確認のみ等が該当）
  RETURN X.protocol = "ssh" AND X.password_auth_attempts = 0
END FUNCTION
```

### Property: Fix Checking

```pascal
// Property: 認証前接続も観測イベントとして記録される
FOR ALL X WHERE isBugCondition(X) DO
  events ← F'(X)
  ASSERT count(events WHERE event_type = "ssh_connection") = 1
    AND events.source_ip = X.source_ip
    AND events.protocol = "ssh"
END FOR
```

### Property: Preservation Checking

```pascal
// Property: 非バグ入力（認証試行あり）に対する挙動は不変
FOR ALL X WHERE NOT isBugCondition(X) DO
  ASSERT F(X) = F'(X)
END FOR
```

すなわち、パスワード認証試行を伴う SSH 接続、および HTTP 接続については、修正前後で発行されるイベント（`ssh_login_attempt` / `http_request` 等）の内容が同一であることを保証する。

### Counterexample（バグの具体例）

- SSH ポートへ TCP 接続し、SSH バージョン交換直後に切断する（`nc` やスキャナによるバナー取得）→ 修正前は `AttackEvent` が 0 件記録される。
- SSH ボットが公開鍵認証のみを試行し、拒否されて切断する → 修正前は `AttackEvent` が 0 件記録される。
