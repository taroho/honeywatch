# Requirements Document

## Introduction

本フィーチャーは、HoneyWatch の Event_Worker が永続化した分類済みの攻撃イベント（`attack_type` / `severity` を付与済みのもの）を Amazon CloudWatch Logs へ転送し、CloudWatch 側の Metric Filter と Alarm によって重大度の高い攻撃をリアルタイムに検知・通知できるようにする機能を提供する。

現状、攻撃イベントは PostgreSQL に永続化され Dashboard で可視化できるが、「いま重大な攻撃が発生している」ことをリアルタイムに検知し外部へ通知する手段が存在しない。本機能により、`severity=HIGH` の攻撃が一定の閾値を超えた際に通知を受け取れるようにする。

本フィーチャーは HoneyWatch 開発フェーズ Phase 3（Security Intelligence）の Alert に相当する。攻撃分類（`attack_type` / `severity` の判定）は従来どおり Event_Worker 内の AttackClassifier が担い、CloudWatch 側では分類を行わない。CloudWatch は分類済み結果の集計・閾値判定・通知のみを担当する。

永続化の真実は従来どおり PostgreSQL にあり、CloudWatch への転送はベストエフォートとする。転送に失敗しても DB への保存および Redis Stream の ACK は従来どおり成功させ、攻撃監視を継続する。

既存データ（本機能の有効化以前に収集済みの Attack_Event）は転送対象外とし、新規イベントのみを転送する。送信先リージョンは EC2 と同一の ap-southeast-2（シドニー）とする。

## Glossary

- **システム**: 本フィーチャーを構成するコンポーネント（Event_Worker、CloudWatch_Forwarder）を総称する HoneyWatch 全体。
- **Event_Worker**: Redis Stream から攻撃イベントを消費し、分類したうえで PostgreSQL に永続化するワーカープロセス。
- **AttackClassifier**: Event_Worker 内で Attack_Event の `attack_type` と `severity` を判定する分類コンポーネント。
- **Attack_Event**: Honeypot が観測した1回の攻撃的アクセスを表すレコード。`attack_events` テーブルに保存される。
- **Classified_Event**: AttackClassifier によって `attack_type` と `severity` が付与され、PostgreSQL への保存が成功した Attack_Event。
- **Severity**: Attack_Event の重大度。HIGH / MEDIUM / LOW のいずれか。
- **CloudWatch_Forwarder**: Classified_Event を CloudWatch_Logs へ送信するコンポーネント。本フィーチャーで新規追加する。
- **CloudWatch_Logs**: Amazon CloudWatch Logs。ログの取り込み・保存・クエリを提供する AWS サービス。
- **Log_Group**: CloudWatch_Logs 上でログストリームを束ねる論理グループ。本機能では `/honeywatch/attack-events` を既定とする。
- **Log_Stream**: Log_Group 内の個々のログの流れ。Event_Worker 単位で作成する。
- **Metric_Filter**: Log_Group に流れたログを検索し、該当件数をメトリクスとして記録する CloudWatch の機能。
- **Alarm**: メトリクスが閾値条件を満たしたときに通知アクションを発火する CloudWatch の機能。
- **転送設定**: CloudWatch_Forwarder の有効/無効、送信先リージョン、Log_Group 名、Log_Stream 名を含む環境変数ベースの設定。
- **ベストエフォート転送**: 転送の失敗が Attack_Event の永続化および Redis Stream の ACK を妨げない転送方式。

## Requirements

### Requirement 1: 転送設定

**User Story:** 運用者として、CloudWatch への転送を環境変数で有効化・設定したい。そうすれば、既存環境に影響を与えずに段階的に機能を導入できる。

#### Acceptance Criteria

1. THE システム SHALL 転送設定（有効/無効、リージョン、Log_Group 名、Log_Stream 名）を環境変数および `core/config.py` の設定項目で指定できる
2. WHERE 転送設定の有効/無効が指定されない、THE システム SHALL 転送を無効（既定で転送しない）として初期化する
3. WHILE 転送設定が無効である、THE Event_Worker SHALL CloudWatch_Logs への送信を一切行わず、PostgreSQL への永続化と Redis Stream の ACK を従来どおり継続する
4. WHERE リージョンが指定されない、THE システム SHALL ap-southeast-2 を既定の送信先リージョンとして使用する
5. WHERE Log_Group 名が指定されない、THE システム SHALL `/honeywatch/attack-events` を既定の Log_Group 名として使用する

### Requirement 2: CloudWatch_Forwarder の初期化

**User Story:** 運用者として、Worker 起動時に CloudWatch 送信先を準備したい。そうすれば、イベント発生時に確実に転送できる。

#### Acceptance Criteria

1. WHEN 転送設定が有効な状態で Event_Worker が起動する、THE CloudWatch_Forwarder SHALL 設定された Log_Group 内に設定された Log_Stream を利用可能な状態にする
2. IF 対象の Log_Stream が存在しない、THEN THE CloudWatch_Forwarder SHALL 当該 Log_Stream を作成する
3. IF 対象の Log_Stream がすでに存在する、THEN THE CloudWatch_Forwarder SHALL 既存の Log_Stream を再利用し、エラーとして扱わない
4. WHEN CloudWatch_Forwarder の初期化が正常に完了する、THE システム SHALL 情報レベルのログを1件出力する
5. IF 転送設定が有効だが初期化に失敗する（権限不足・リージョン不一致・接続不可など）、THEN THE Event_Worker SHALL 原因を示す警告レベルのログを1件出力し、CloudWatch 転送を無効化した状態で PostgreSQL への永続化を継続する

### Requirement 3: 分類済みイベントの転送

**User Story:** セキュリティエンジニアとして、分類済みの攻撃イベントを CloudWatch に送りたい。そうすれば、重大度に基づく検知を CloudWatch 側で行える。

#### Acceptance Criteria

1. WHEN Classified_Event の PostgreSQL への保存が成功する、THE CloudWatch_Forwarder SHALL 当該イベントを CloudWatch_Logs へ送信する
2. THE CloudWatch_Forwarder SHALL 送信するログを、`severity` をトップレベルのキーに含む JSON 形式で出力する
3. THE CloudWatch_Forwarder SHALL 送信するログに、イベント識別子・タイムスタンプ・送信元 IP・宛先ポート・プロトコル・イベント種別・`attack_type`・`severity` を含める
4. WHILE 転送設定が有効である、THE CloudWatch_Forwarder SHALL 保存に成功したすべての Classified_Event を送信対象とする
5. IF PostgreSQL への保存が成功しない（最大リトライ回数を超えて ACK されない）、THEN THE CloudWatch_Forwarder SHALL 当該イベントを送信しない

### Requirement 4: ベストエフォート転送とエラーハンドリング

**User Story:** 運用者として、CloudWatch 転送の失敗が攻撃監視を止めないようにしたい。そうすれば、転送側の障害時も永続化と監視を継続できる。

#### Acceptance Criteria

1. THE システム SHALL CloudWatch_Logs への転送をベストエフォート転送として扱う
2. IF CloudWatch_Logs への送信が失敗する（例外・権限エラー・ネットワークエラーなど）、THEN THE システム SHALL 原因を示す警告レベルのログを1件出力し、PostgreSQL への保存と Redis Stream の ACK を従来どおり成功させる
3. THE CloudWatch_Forwarder SHALL 転送処理において Event_Worker の非同期イベントループを長時間ブロックしない
4. IF CloudWatch_Logs への送信が連続して失敗する、THEN THE Event_Worker SHALL イベント消費ループを停止せず、後続イベントの永続化を継続する

### Requirement 5: 既存データとデータ範囲

**User Story:** 運用者として、既存データを転送対象外にしたい。そうすれば、転送コストと誤ったアラート発火を抑えられる。

#### Acceptance Criteria

1. THE システム SHALL 本機能の有効化以前に収集済みの Attack_Event を CloudWatch_Logs へ転送しない
2. WHEN 転送設定が有効化された後に新たに保存される Classified_Event が発生する、THE CloudWatch_Forwarder SHALL 当該新規イベントのみを送信対象とする
3. THE システム SHALL 既存データの一括転送（バックフィル）を本フィーチャーの実装範囲に含めない
