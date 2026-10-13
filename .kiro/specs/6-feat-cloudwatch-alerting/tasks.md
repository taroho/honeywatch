# Implementation Plan: CloudWatch Logs 連携による攻撃検知・通知

## Overview

本実装計画は、design.md に基づき、Event_Worker が永続化した分類済み攻撃イベントを Amazon CloudWatch Logs へベストエフォートで転送し、CloudWatch 側の Metric Filter / Alarm で `severity=HIGH` を検知・通知できるようにする機能を段階的に構築する。

実装は既存コード構成に合わせ、次の依存順で進める。

1. 依存ライブラリ追加・設定（`pyproject.toml`, `core/config.py`, `.env`）
2. 送信ペイロード構築と `CloudWatchForwarder` の実装（`alert/cloudwatch.py`）
3. `EventWorker` への統合（`tasks/workers.py`）
4. プロパティテスト・ユニットテスト・統合テスト・検証

分類は従来どおり `AttackClassifier`（既存）が担い、本機能では分類ロジックに手を入れない。CloudWatch 側の AWS リソース（Log_Group / Metric_Filter / Alarm / SNS）の作成は手順書 `docs/cloudwatch-setup.md` に記載済みで、本計画のコード実装範囲外とする。既存データのバックフィルは実装しない（スコープ外）。`attack_events` テーブルのスキーマは変更しないため、マイグレーションタスクは作成しない。

テストは pytest + Hypothesis を用い、design の Correctness Properties（Property 1〜5）を検証する。AWS への実接続は行わず、`moto` または boto3 クライアントのモックで完結させる。

## Tasks

- [ ] 1. 依存ライブラリと CloudWatch 設定のセットアップ
  - [ ] 1.1 依存ライブラリを追加し `uv sync` を実行する
    - `pyproject.toml` の本体 `dependencies` に `boto3==1.35.0` を追加する
    - `pyproject.toml` の dev 依存に `moto==5.0.0` を追加する
    - `uv sync` を実行してロックファイルを更新する
    - _Requirements: 3.1_

  - [ ] 1.2 `CloudWatchSettings` を追加し `Settings` に統合する
    - `src/honeywatch/core/config.py` に `CloudWatchSettings`（`env_prefix="CLOUDWATCH_"`, `enabled`（既定 False）, `region`（既定 ap-southeast-2）, `log_group`（既定 /honeywatch/attack-events）, `log_stream`（既定 worker-1））を追加する
    - `Settings` に `cloudwatch: CloudWatchSettings = CloudWatchSettings()` を統合する
    - _Requirements: 1.1, 1.2, 1.4, 1.5_

  - [ ] 1.3 環境変数テンプレートを追記する
    - `.env`（および `.env.example` が存在すれば同様に）へ `CLOUDWATCH_ENABLED=false`, `CLOUDWATCH_REGION=ap-southeast-2`, `CLOUDWATCH_LOG_GROUP=/honeywatch/attack-events`, `CLOUDWATCH_LOG_STREAM=worker-1` を追加する
    - 既定無効のままで既存環境に影響しないことを確認する
    - _Requirements: 1.1, 1.2_

- [ ] 2. 送信ペイロード構築と CloudWatchForwarder を実装する
  - [ ] 2.1 `build_log_payload` を実装する
    - `src/honeywatch/alert/cloudwatch.py` に `build_log_payload(model)` を実装する
    - `severity` をトップレベルキーに置き、event_id・timestamp（ISO 8601）・source_ip・destination_port・protocol・event_type・attack_type・severity を含める
    - _Requirements: 3.2, 3.3_

  - [ ] 2.2 `CloudWatchForwarder` の構築と初期化を実装する
    - `src/honeywatch/alert/cloudwatch.py` に `CloudWatchForwarder.__init__` / `create(settings)` / `initialize()` / `close()` を実装する
    - `create` は `enabled=False` のとき `None` を返す（転送無効）
    - `initialize` は `boto3.client("logs", region_name=region)` を生成し、`create_log_stream` を `asyncio.to_thread` で実行する
    - 成功で info ログ1件・`True` を返す
    - `ResourceAlreadyExistsException` は成功扱いで `True` を返す（既存 Log_Stream 再利用）
    - 権限不足・リージョン不一致・接続不可の例外は warning ログ1件・`False` を返す
    - _Requirements: 1.2, 2.1, 2.2, 2.3, 2.4, 2.5_

  - [ ] 2.3 `CloudWatchForwarder.forward` を実装する
    - `src/honeywatch/alert/cloudwatch.py` に `forward(model)` を実装する
    - `build_log_payload` の結果を `json.dumps` し、`PutLogEvents`（`logGroupName` / `logStreamName` / `logEvents=[{timestamp(ms), message}]`）を `asyncio.to_thread` で実行する
    - 送信失敗（`ClientError` / `BotoCoreError` / その他）は例外を内部で捕捉し warning ログ1件のみ残す（再送しない・例外を伝播させない）
    - sequenceToken は管理しない（API 仕様に委ねる）
    - ログは既存の `core/logging.py`（structlog）を用いる
    - _Requirements: 3.1, 4.1, 4.2, 4.3_

  - [ ]* 2.4 `CloudWatchForwarder` のプロパティテストを書く
    - `tests/test_alert/test_cloudwatch.py` に Hypothesis によるプロパティテストを実装し、boto3 クライアントをモックして AWS に接続しない形で検証する
    - 各テストに `# Feature: 6-feat-cloudwatch-alerting, Property N: ...` タグを付す
    - **Property 1: 送信ペイロードは severity をトップレベルに持ち必須フィールドを欠かさない**（Validates: Requirements 3.2, 3.3）
    - **Property 2: 送信失敗は例外を伝播させず監視を止めない**（Validates: Requirements 4.1, 4.2, 4.4）
    - **Property 3: 転送無効時はクライアントを構築せず送信しない**（Validates: Requirements 1.2, 1.3）
    - **Property 4: 既存の Log_Stream は初期化失敗にならない**（Validates: Requirements 2.2, 2.3）
    - **Property 5: 初期化が権限・接続エラーで失敗しても永続化は継続する**（Validates: Requirements 2.5, 4.4）

  - [ ]* 2.5 `CloudWatchForwarder` のユニットテストを書く
    - `tests/test_alert/test_cloudwatch.py` に初期化分岐・送信・ログ出力の例示テストを実装する
    - 初期化成功で info ログ1件・`True`（2.1, 2.4）、初期化失敗で warning ログ1件・`False`（2.5）
    - 送信成功で `PutLogEvents` が期待する `logGroupName`/`logStreamName`/`message`（severity 含む JSON）で1回呼ばれる（3.1, 3.2, 3.3）
    - `moto` を用いた Log_Group 作成 → initialize → forward → ログ取得の往復（任意）
    - _Requirements: 2.1, 2.4, 2.5, 3.1, 3.2, 3.3_

- [ ] 3. EventWorker に CloudWatch 転送を統合する
  - [ ] 3.1 Forwarder の保持と起動時初期化を実装する
    - `src/honeywatch/tasks/workers.py` の `EventWorker.__init__` に `self._cloudwatch_forwarder: CloudWatchForwarder | None = None` を追加する
    - `start()` の分類コンポーネント初期化と同じ箇所で `CloudWatchForwarder.create(settings.cloudwatch)` を呼び、`None` でなければ `initialize()` を実行する
    - 初期化失敗（`False`）時は `self._cloudwatch_forwarder = None` として転送を無効化し、永続化を継続する
    - `stop()` で Forwarder が存在すれば `close()` する
    - _Requirements: 1.3, 2.1, 2.5, 4.4_

  - [ ] 3.2 保存成功後・ACK 前の送信を実装する
    - `src/honeywatch/tasks/workers.py` の `_process_event` で、DB 保存成功後・`ack(entry_id)` 呼び出しの直前に、Forwarder が存在すれば `await self._cloudwatch_forwarder.forward(model)` を呼ぶ
    - 転送の成否に関わらず ACK を実行する（転送失敗で ACK を妨げない）
    - 保存が最大リトライ超過で ACK されないイベントは送信しない（既存挙動を維持）
    - _Requirements: 3.1, 3.5, 4.2, 4.4, 5.1, 5.2_

  - [ ]* 3.3 EventWorker 統合の統合テストを書く
    - `tests/test_tasks/test_worker_cloudwatch.py`（既存の tasks テスト構成に合わせて配置）に、保存成功モック + 送信モックで `_process_event` を実行する統合テストを実装する
    - 「保存成功 → forward 呼び出し → ACK」の順序を検証する（3.1）
    - 送信失敗時でも ACK が実行されることを検証する（4.2）
    - 転送無効（Forwarder=None）時は forward が呼ばれず ACK されることを検証する（1.3）
    - 保存失敗（最大リトライ超過）イベントが送信されないことを検証する（3.5）
    - _Requirements: 1.3, 3.1, 3.5, 4.2_

- [ ] 4. Checkpoint - テストと静的解析が通ることを確認する
  - Ensure all tests pass, ask the user if questions arise.
  - `uv run pytest`, `uv run mypy .`, `uv run ruff check .` を実行し、エラーがないことを確認する
  - `CLOUDWATCH_ENABLED=false`（既定）で既存のテストが従来どおりグリーンであることを確認する

## Notes

- `*` を付したサブタスクはオプション（テスト）で、MVP を優先する場合はスキップできる。トップレベルタスクにはオプション印を付けない。
- CloudWatch 側の AWS リソース（Log_Group / Metric_Filter / Alarm / SNS）と IAM 権限の作成は手順書 `docs/cloudwatch-setup.md` に記載済みで、本計画のコード実装範囲外とする。
- 分類（`attack_type` / `severity`）は既存の `AttackClassifier` が担い、本計画では分類ロジックを変更しない。
- 既存データのバックフィルは実装しない（Requirement 5.3、スコープ外）。
- `attack_events` のスキーマは変更しないため、マイグレーションタスクは含めない。
- 転送はベストエフォートであり、初期化失敗・送信失敗のいずれでも永続化と ACK を継続する。
- プロパティテストは design.md の Correctness Properties（Property 1〜5）を検証し、各テストに `# Feature: 6-feat-cloudwatch-alerting, Property N: ...` タグを付す。AWS への実接続は行わず `moto`／モックで完結させる。
- Checkpoint では `uv run pytest` / `uv run mypy .` / `uv run ruff check .` による検証を行う（この環境での実行は tech steering の「sh 実行 → txt 読み取り」手順に従う）。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["2.1", "2.2"] },
    { "id": 2, "tasks": ["2.3"] },
    { "id": 3, "tasks": ["2.4", "2.5", "3.1"] },
    { "id": 4, "tasks": ["3.2"] },
    { "id": 5, "tasks": ["3.3"] },
    { "id": 6, "tasks": ["4"] }
  ]
}
```
