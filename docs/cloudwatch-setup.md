# CloudWatch Logs 連携 セットアップ

## 概要

HoneyWatch の CloudWatch 連携は、Event Worker が **分類済み**の攻撃イベント
（`attack_type` / `severity` 付き）を Amazon CloudWatch Logs へ転送し、CloudWatch 側の
Metric Filter + Alarm で異常を検知・通知する仕組みである。

役割分担は次のとおり明確に分ける。

- **分類はアプリ内（Worker の `AttackClassifier`）で実施する。** CloudWatch 側では分類しない。
  `brute_force` / `port_scan` のように複数イベントの状態（IPContext）をまたぐ判定は
  Metric Filter（1行のパターンマッチ）では表現できないため、分類は従来どおり Worker が担う。
- **CloudWatch は「分類済み結果の集計・閾値判定・通知」だけを担う。** Dashboard（PostgreSQL）と
  同じ分類結果を送るため、Dashboard と CloudWatch で検知内容が食い違わない。

永続化の真実は従来どおり PostgreSQL にあり、CloudWatch 転送は**ベストエフォート**である。
転送に失敗しても DB 保存と Redis の ACK は従来どおり成功させ、攻撃監視は継続する。

### 検知対象（初期設定）

- `severity = HIGH` のイベントを検知対象とする。
- 通知は CloudWatch Alarm → SNS 経由で行う（通知先は後述の手順で設定する）。

### 既存データの扱い

- **既存データ（過去に収集済みのイベント）は転送しない。** CloudWatch の目的はリアルタイム検知で
  あり、過去ログを流し込んでも Alarm はタイムスタンプのずれで誤発火・埋没するだけで意味がない。
  過去データの分析は Dashboard / 分析 API（PostgreSQL）が担う。
- 本連携では**新規イベントの常時転送のみ**を実装する。

## 全体構成

```
Event Worker（分類する）
  → attack_type / severity を付与
  → PostgreSQL に保存（既存フロー、ここが永続化の真実）
  → CloudWatch Logs に分類済みイベントを送信（本連携で追加・ベストエフォート）

CloudWatch Logs（分類しない）
  → Metric Filter で severity=HIGH をカウント
  → Alarm で閾値（例: 5分で N 件）を判定
  → SNS Topic → メール等へ通知
```

## 前提

- EC2 上で Docker Compose により Worker が稼働していること。
- リージョンは **ap-southeast-2（シドニー）**。EC2 と同一リージョンに揃える。
- EC2 にインスタンスプロファイル（IAM ロール）を割り当てられること。
  アクセスキーをコンテナに直接渡さず、インスタンスロールで権限を付与する方針とする。

---

## 手順 1: IAM 権限の付与

EC2 のインスタンスロールに、CloudWatch Logs への書き込み権限を付与する。
最小権限の原則に従い、対象ロググループに限定する。

### 1-1. ポリシーを作成する

次の内容で IAM ポリシー（例: `HoneyWatchCloudWatchLogsWrite`）を作成する。
`<ACCOUNT_ID>` は自分の AWS アカウント ID に置き換える。

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "HoneyWatchLogsWrite",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:ap-southeast-2:<ACCOUNT_ID>:log-group:/honeywatch/attack-events:*"
    }
  ]
}
```

- ロググループを手順 2 で手動作成する場合、`logs:CreateLogGroup` は不要。
- アプリ側に自動作成させたい場合のみ `logs:CreateLogGroup` を追加する（本手順では手動作成を推奨）。

### 1-2. ロールにアタッチする

EC2 にアタッチ済みのインスタンスロールに、作成したポリシーをアタッチする。
インスタンスロールが未割り当ての場合は、ロールを新規作成して EC2 にアタッチする。

---

## 手順 2: ロググループの作成

AWS CLI または マネジメントコンソールでロググループを作成する。

```bash
aws logs create-log-group \
  --log-group-name /honeywatch/attack-events \
  --region ap-southeast-2
```

保持期間を設定する（コスト抑制のため。例: 30 日）。

```bash
aws logs put-retention-policy \
  --log-group-name /honeywatch/attack-events \
  --retention-in-days 30 \
  --region ap-southeast-2
```

> ログストリームは Worker が起動時に自動作成する（`logs:CreateLogStream`）。

---

## 手順 3: アプリケーション設定（環境変数）

`.env`（テンプレートは `.env.example`）に次を設定する。
`CLOUDWATCH_ENABLED=false`（既定）のままなら転送は行われず、既存環境に影響しない。

| 環境変数 | 既定値 | 説明 |
|----------|--------|------|
| `CLOUDWATCH_ENABLED` | `false` | 転送の有効/無効。本番で有効にする場合は `true` |
| `CLOUDWATCH_REGION` | `ap-southeast-2` | 送信先リージョン。EC2 と揃える |
| `CLOUDWATCH_LOG_GROUP` | `/honeywatch/attack-events` | ロググループ名 |
| `CLOUDWATCH_LOG_STREAM` | `worker-1` | ログストリーム名。Worker 名に合わせる |

```
CLOUDWATCH_ENABLED=true
CLOUDWATCH_REGION=ap-southeast-2
CLOUDWATCH_LOG_GROUP=/honeywatch/attack-events
CLOUDWATCH_LOG_STREAM=worker-1
```

設定後、Worker を再起動して反映する。

```bash
docker compose up -d worker
```

### 送信されるログの形式

Worker は DB 保存成功後、分類済みイベントを次の JSON 形式で送信する。
`severity` を Metric Filter で参照するため、トップレベルのキーとして出力する。

```json
{
  "event_id": "…",
  "timestamp": "2026-09-01T03:16:00Z",
  "source_ip": "203.0.113.10",
  "destination_port": 22,
  "protocol": "ssh",
  "event_type": "ssh_auth",
  "attack_type": "brute_force",
  "severity": "HIGH"
}
```

---

## 手順 4: Metric Filter の作成

ロググループに Metric Filter を作成し、`severity=HIGH` のイベント件数をメトリクス化する。

```bash
aws logs put-metric-filter \
  --log-group-name /honeywatch/attack-events \
  --filter-name HighSeverityAttacks \
  --filter-pattern '{ $.severity = "HIGH" }' \
  --metric-transformations \
      metricName=HighSeverityAttackCount,metricNamespace=HoneyWatch,metricValue=1,defaultValue=0 \
  --region ap-southeast-2
```

- `filter-pattern` の `{ $.severity = "HIGH" }` は JSON ログの `severity` フィールドを参照する。
- `defaultValue=0` を指定することで、該当なしの期間も 0 が記録され、Alarm 評価が安定する。

---

## 手順 5: SNS トピックと通知先の設定

Alarm の通知先となる SNS トピックを作成し、サブスクリプション（例: メール）を登録する。

```bash
aws sns create-topic \
  --name honeywatch-alerts \
  --region ap-southeast-2
```

出力された Topic ARN に対してメールを購読する（`<TOPIC_ARN>` は上の出力に置き換える）。

```bash
aws sns subscribe \
  --topic-arn <TOPIC_ARN> \
  --protocol email \
  --notification-endpoint you@example.com \
  --region ap-southeast-2
```

> 購読確認メールが届くので、本文のリンクから confirm する。confirm しないと通知は届かない。

---

## 手順 6: CloudWatch Alarm の作成

Metric Filter のメトリクスに対して Alarm を作成する。
例として「5 分間に HIGH severity が 10 件以上」で発報する設定にする。
`<TOPIC_ARN>` は手順 5 のものに置き換える。

```bash
aws cloudwatch put-metric-alarm \
  --alarm-name HoneyWatch-HighSeverity \
  --namespace HoneyWatch \
  --metric-name HighSeverityAttackCount \
  --statistic Sum \
  --period 300 \
  --evaluation-periods 1 \
  --threshold 10 \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --treat-missing-data notBreaching \
  --alarm-actions <TOPIC_ARN> \
  --region ap-southeast-2
```

- `--period 300`（5 分） × `--evaluation-periods 1` で「直近 5 分の合計」を評価する。
- `--threshold` は実データの分布を見て調整する（memo.md の閾値チューニング方針と同様）。
- `--treat-missing-data notBreaching` で、イベントが無い期間に誤発報しないようにする。

---

## 動作確認

1. `CLOUDWATCH_ENABLED=true` で Worker を再起動する。
2. Worker ログに CloudWatch 初期化（ログストリーム作成）が出ることを確認する。

   ```bash
   docker compose logs -f worker
   ```

3. CloudWatch Logs コンソール（ap-southeast-2）でロググループ
   `/honeywatch/attack-events` にイベントが流れていることを確認する。
4. HIGH severity イベントが閾値を超えた際に、SNS 購読先へ通知が届くことを確認する。
5. CloudWatch Logs Insights で件数を確認する例:

   ```
   fields @timestamp, source_ip, attack_type, severity
   | filter severity = "HIGH"
   | sort @timestamp desc
   | limit 50
   ```

---

## トラブルシューティング

| 症状 | 原因と対処 |
|------|-----------|
| ログが CloudWatch に出ない | `CLOUDWATCH_ENABLED=true` になっているか、Worker を再起動したか確認する |
| `AccessDenied` が Worker ログに出る | IAM ポリシー（手順 1）の Resource とロググループ名が一致しているか確認する |
| リージョン不一致で送信失敗 | `CLOUDWATCH_REGION` が EC2 と同じ `ap-southeast-2` か確認する |
| Alarm が発報しない | Metric Filter の `filter-pattern` が実ログの JSON キーと一致しているか確認する |
| 通知が届かない | SNS サブスクリプションの confirm が完了しているか確認する |
| 転送でエラーが出ても監視は継続 | CloudWatch 転送はベストエフォート。失敗は warning ログに記録され、DB 保存は成功している |

## コスト・運用に関する注意

- CloudWatch Logs は取り込み量・保存量・PutLogEvents 回数で課金される。t3.micro の小規模運用に
  合わせ、**既存データは転送せず新規のみ**とし、保持期間（手順 2）を短め（例: 30 日）に設定する。
- 大量の SSH Brute Force が続く状況では転送件数も増える。コストが気になる場合は、Worker 側の
  送信対象を `severity=HIGH` のみに絞る運用も検討する（本連携は全件送信を既定とする）。
