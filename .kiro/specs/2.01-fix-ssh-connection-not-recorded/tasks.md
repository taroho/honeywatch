# Implementation Plan

## Overview

本実装計画は、bugfix.md（Requirements）と design.md（Fix Implementation / Testing Strategy）に基づき、
探索的バグ修正ワークフロー（探索 → 保存 → 実装 → 検証）で SSH 認証前接続の記録漏れを修正する。

対象コード変更ファイルは `src/honeywatch/honeypot/ssh.py` の 1 ファイルのみ。
DB マイグレーション不要・HTTP Honeypot 無変更・新依存追加なし。
テストは `tests/test_honeypot/` に pytest + pytest-asyncio で配置する。

> **テスト方式に関する前提（重要）**:
> `hypothesis` は現状 `pyproject.toml` に未導入。design.md では Preservation に property-based testing を推奨しているが、
> 「新依存を追加しない」制約を優先する。したがって property-based の観点（`self._attempts` の値域による排他性、
> ランダム入力での不変条件）は **pytest のパラメータ化テスト（`@pytest.mark.parametrize`）で複数ケースを列挙して代替**する。
> hypothesis の導入可否はタスク 0 でユーザーに確認し、承認された場合のみ property-based に切り替える。

## Tasks

- [x] 0. テスト方式の確認（hypothesis 導入可否）
  - `hypothesis` は `pyproject.toml` の `dev` 依存に未導入であることを確認する
  - property-based testing（hypothesis）を導入するか、パラメータ化テストで代替するかをユーザーに確認する
  - 未導入のまま進める場合は、Property 1 / Property 2 のテストを `@pytest.mark.parametrize` による複数ケース列挙で実装する方針とする
  - `tests/test_honeypot/__init__.py` を作成し、テストパッケージを用意する
  - _Requirements: 2.1, 3.1_

- [ ] 1. バグ条件の探索テストを作成する（修正前に実施）
  - **Property 1: Bug Condition** - 認証試行なし接続の記録漏れ
  - **CRITICAL**: このテストは修正前コードで必ず FAIL する。FAIL することがバグの存在を裏付ける
  - **DO NOT**: テストが失敗してもテストやコードを修正しない（この段階では失敗が正しい結果）
  - **NOTE**: このテストは期待挙動をエンコードしており、実装後に PASS することで修正を検証する
  - **GOAL**: バグを示す反例を surface する（認証試行なし接続で `emit_event` が呼ばれないこと）
  - **Scoped PBT Approach**: 決定的なバグのため、具体的な失敗ケースにスコープする（`self._attempts == 0` かつ `protocol == "ssh"`）
  - `tests/test_honeypot/test_ssh_connection_event.py` を作成する
  - `SSHHoneypotServer` をインスタンス化し、`SSHHoneypot.emit_event` をモック（AsyncMock）して発行内容を捕捉する
  - `connection_made`（`peername` を含むダミー conn）→ `validate_password` を呼ばず `connection_lost(None)` を実行するシーケンスをテストする（design: Banner Grab Test）
  - `connection_lost(exc=Exception(...))` かつ `self._attempts == 0` のケースもテストする（design: Connection With Exception Test）
  - `client_version` が空文字のケースでも `ssh_connection` 発行が期待されることをテストに含める（Requirement 2.3）
  - 期待するアサーション（実装後に満たされるべき Expected Behavior）:
    - `event_type == "ssh_connection"` のイベントがちょうど 1 件発行される
    - `source_ip == 接続元 IP`、`protocol == "ssh"`、`destination_port == honeypot.port`
    - `raw_data["auth_attempts"] == 0`、`raw_data["connection_duration"] >= 0`、`raw_data` に `client_version` を含む
  - 修正前コード（UNFIXED）で実行する
  - **EXPECTED OUTCOME**: テストは FAIL する（`connection_lost` は debug ログのみで `emit_event` を呼ばないため。これがバグの存在を証明する）
  - 発見した反例をドキュメント化する（例: 「認証試行なし切断で emit_event が一度も呼ばれず、ssh_connection が 0 件」）
  - テストを作成・実行し、失敗を記録した時点でタスク完了とする
  - _Requirements: 2.1, 2.2, 2.3_

- [ ] 2. 保存（Preservation）テストを作成する（修正前に実施）
  - **Property 2: Preservation** - 認証試行あり接続および HTTP の不変性
  - **IMPORTANT**: observation-first メソドロジーに従う（修正前コードで実際の挙動を観察してから固定する）
  - `tests/test_honeypot/test_ssh_preservation.py` を作成する
  - 観察と固定（design: Preservation Checking Test Cases）:
    - **Auth Attempt Preservation**: `connection_made` → `validate_password("root", "123456")`（`self._attempts >= 1`）→ `connection_lost(None)` のシーケンスで、`ssh_login_attempt` が従来どおり 1 件記録され、かつ `ssh_connection` が発行されないことを検証する
    - **SSHEventData Structure Preservation**: `ssh_login_attempt` の `raw_data` が `username` / `password` / `client_version` / `connection_duration` / `auth_success` を持つことを検証する
    - **排他性（property-based 観点 / パラメータ化で代替）**: `self._attempts` の値域（0 と 1 以上の複数値）で発行イベント種別が排他になること（`0` → `ssh_connection` のみ、`>= 1` → `ssh_login_attempt` のみで `ssh_connection` なし）を `@pytest.mark.parametrize` で検証する
    - **HTTP No Impact**: HTTP Honeypot（`src/honeywatch/honeypot/http.py`）の `http_request` 記録が本修正の影響を受けないことを検証する（`tests/test_honeypot/test_http_preservation.py` として分けてもよい）
    - **分類器の素通り確認**: `event_type="ssh_connection"`（`raw_data` に `username`/`password` を含まない）の `AttackEvent` を `detection` の分類器に通しても `_is_credential_attack` が素通りし、分類が破綻しないことを検証する（Requirement 3.5 / 2.4）
  - 修正前コード（UNFIXED）で実行する
  - **EXPECTED OUTCOME**: すべての保存テストが PASS する（保存すべきベースライン挙動を確認できる）
  - テストを作成・実行し、修正前コードで PASS することを記録した時点でタスク完了とする
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [ ] 3. SSH 認証前接続の記録漏れを修正する

  - [x] 3.1 修正を実装する
    - `SSHHoneypotServer.__init__` に `self._pending_tasks: set[asyncio.Task[None]] = set()` を追加する
    - `connection_lost(self, exc)` を修正し、`self._attempts == 0` のとき**のみ** `event_type="ssh_connection"` の `AttackEvent` を 1 件構築する（`self._attempts >= 1` では発行しない＝二重記録防止）
    - `raw_data` は案B（dict 直接構築）とし、`{"client_version": self._client_version, "connection_duration": time.time() - self._conn_start, "auth_attempts": 0}` を設定する（`username`/`password` は含めない）
    - イベントフィールドの取得元: `source_ip = self._peer_addr[0] if self._peer_addr else "0.0.0.0"`、`source_port = self._peer_addr[1] if self._peer_addr else 0`、`destination_port = self._honeypot.port`、`protocol = "ssh"`
    - 同期→async ブリッジ: `asyncio.create_task(self._honeypot.emit_event(event))` でスケジュールし、`self._pending_tasks.add(task)` と `task.add_done_callback(self._pending_tasks.discard)` で GC 防止・完了時除去を行う
    - フォールバック: `asyncio.get_running_loop()` が `RuntimeError` の場合はイベント発行を諦め、`logger.warning` のみとし例外を伝播させない
    - `validate_password` / `connection_made` / `begin_auth` / `password_auth_supported` / `SSHEventData` / `AttackEvent` / 分類器 / HTTP Honeypot / DB モデル / マイグレーションは変更しない
    - _Bug_Condition: isBugCondition(input) = (input.protocol == "ssh" AND input.password_auth_attempts == 0)（design）_
    - _Expected_Behavior: バグ条件成立時に ssh_connection の AttackEvent をちょうど 1 件発行（design: Property 1）_
    - _Preservation: 認証試行あり接続の ssh_login_attempt 記録・HTTP 記録・既存 event_type 分類を不変（design: Preservation Requirements）_
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ] 3.2 バグ条件の探索テストが PASS することを確認する
    - **Property 1: Expected Behavior** - 認証試行なし接続の記録
    - **IMPORTANT**: タスク 1 と同じテストを再実行する（新しいテストは書かない）
    - タスク 1 のテストは期待挙動をエンコードしており、PASS することで Expected Behavior の充足を確認できる
    - タスク 1 の探索テストを修正後コードで実行する
    - **EXPECTED OUTCOME**: テストが PASS する（バグが修正されたことを確認）
    - _Requirements: 2.1, 2.2, 2.3_

  - [ ] 3.3 保存テストが引き続き PASS することを確認する
    - **Property 2: Preservation** - 認証試行あり接続および HTTP の不変性
    - **IMPORTANT**: タスク 2 と同じテストを再実行する（新しいテストは書かない）
    - タスク 2 の保存テストを修正後コードで実行する
    - **EXPECTED OUTCOME**: テストが PASS する（regression がないことを確認）
    - 修正後もすべての保存テストが PASS することを確認する
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [ ] 4. Checkpoint - 全テストと静的解析を通す
  - `uv run ruff check .` を実行し、リントエラーがないことを確認する
  - `uv run ruff format .` を実行し、フォーマットを整える
  - `uv run mypy .` を実行し、型エラーがないことを確認する（`self._pending_tasks: set[asyncio.Task[None]]` の型付けを含む）
  - `uv run pytest` を実行し、全テスト（探索テスト・保存テスト・既存テスト）が PASS することを確認する
  - 影響範囲を確認する: 変更は `src/honeywatch/honeypot/ssh.py` の 1 ファイルに閉じ、HTTP・DB・分類器・マイグレーションに影響がないこと
  - 疑問が生じた場合はユーザーに確認する

- [ ] 5. 本番反映時の注意点の共有（コード変更なし）
  - 本修正により `event_type="ssh_connection"` が新規に増加するため、本番 EC2 反映後は SSH イベント件数が急増し得ることをユーザーに共有する
  - ダッシュボード集計・分類が新 `event_type` を破綻なく扱うこと（Requirement 2.4）を反映前に確認するよう注意喚起する（デプロイ・運用作業自体は本タスクの範囲外）
  - _Requirements: 2.4_

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["0"], "description": "テスト方式確認・test_honeypot パッケージ用意" },
    { "wave": 2, "tasks": ["1", "2"], "description": "Bug Condition 探索テスト(修正前FAIL)と Preservation テスト(修正前PASS)を並行作成" },
    { "wave": 3, "tasks": ["3.1"], "description": "ssh.py の修正実装" },
    { "wave": 4, "tasks": ["3.2", "3.3"], "description": "Property 1 / Property 2 の再検証(PASS)" },
    { "wave": 5, "tasks": ["4"], "description": "Checkpoint: ruff / mypy / pytest" },
    { "wave": 6, "tasks": ["5"], "description": "本番反映の注意点共有(コード変更なし)" }
  ]
}
```

```
                    ┌─────────────────────────────┐
                    │ 0. テスト方式確認             │
                    │   (test_honeypot パッケージ) │
                    └──────────────┬──────────────┘
                                   │ 前提
                    ┌──────────────┴──────────────┐
                    ▼                              ▼
      ┌───────────────────────────┐  ┌───────────────────────────┐
      │ 1. Bug Condition 探索テスト │  │ 2. Preservation テスト     │
      │    (修正前 FAIL)           │  │    (修正前 PASS)           │
      └──────────────┬────────────┘  └──────────────┬────────────┘
                     │  (両方とも 3.1 の前に完成)     │
                     └───────────────┬───────────────┘
                                     ▼
                    ┌─────────────────────────────┐
                    │ 3.1 修正実装 (ssh.py)        │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                              ▼
      ┌───────────────────────────┐  ┌───────────────────────────┐
      │ 3.2 Property 1 再検証 PASS │  │ 3.3 Property 2 再検証 PASS │
      └──────────────┬────────────┘  └──────────────┬────────────┘
                     └───────────────┬───────────────┘
                                     ▼
                    ┌─────────────────────────────┐
                    │ 4. Checkpoint                │
                    │   (ruff / mypy / pytest)     │
                    └──────────────┬──────────────┘
                                   ▼
                    ┌─────────────────────────────┐
                    │ 5. 本番反映の注意点共有       │
                    │   (コード変更なし)           │
                    └─────────────────────────────┘
```

依存関係の説明:

- タスク 0（テスト方式確認・`test_honeypot` パッケージ用意）は、タスク 1 と 2 の前提となる。
- タスク 1（Bug Condition 探索テスト、修正前は FAIL）とタスク 2（Preservation テスト、修正前は PASS）は互いに独立しており、いずれもタスク 3.1 の前に完成させる。
- タスク 3.1（修正実装）が完了してから、タスク 3.2（Property 1 の再検証で PASS）とタスク 3.3（Property 2 の再検証で PASS）を実施する。
- タスク 4（Checkpoint: ruff / mypy / pytest）は 3 系（3.1・3.2・3.3）の完了後に実施する。
- タスク 5（本番反映の注意点共有、コード変更なし）を最後に実施する。

## Notes

- 本 spec は bugfix（requirements-first）ワークフローに従う。実装着手前に bugfix.md → design.md → tasks.md の順で確認・承認を得ること。
- コード変更は `src/honeywatch/honeypot/ssh.py` の 1 ファイルに限定する。DB マイグレーション不要、HTTP Honeypot 無変更、新依存追加なし。
- テストは修正前コードで先に作成し、Bug Condition テストが FAIL・Preservation テストが PASS することを確認してから実装に入る。
- `hypothesis` 未導入のため property-based testing はパラメータ化テスト（`@pytest.mark.parametrize`）で代替する。導入する場合はタスク 0 で合意し、`pyproject.toml` の dev 依存追加を別途行う。
- 実装後の本番 EC2 反映（Docker 再ビルド・再起動）は運用作業であり、本タスクの範囲外とする。
