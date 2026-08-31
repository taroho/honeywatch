# Deployment

## 概要

HoneyWatch を AWS EC2 に単一インスタンス構成でデプロイし、実際の攻撃トラフィックを収集する手順です。開発時のローカル Docker Compose 構成をそのまま本番でも使用します。

## 最終構成

```
Cloud (AWS)
└── HoneyWatch 専用 EC2 (t3.micro / Ubuntu)
     ├── Honeypot コンテナ（外部公開: SSH 2222, HTTP 8080）
     ├── Event Worker コンテナ
     ├── API コンテナ（管理用: 8000）
     ├── Dashboard コンテナ（管理用: 3000）
     ├── PostgreSQL コンテナ（内部のみ）
     └── Redis コンテナ（内部のみ）
```

## 事前準備

### AWS アカウント

1. AWS アカウントを作成
2. ルートアカウントに MFA を設定
3. IAM ユーザーを作成し、普段はそちらを使用
4. **予算アラートを設定**（AWS Budgets → $15 → メール通知）

### IAM セットアップ

ルートアカウントは封印し、日常操作は IAM ユーザーで行う。

**ユーザー構成:**

- EC2 を起動・管理するための管理用ユーザーを1つ作成する
- グループ（例: `honeywatch-admins`）を作り、ポリシーはグループにアタッチする
  （ユーザーへの直接アタッチより管理しやすい）

**アクセス設定:**

| 項目 | 設定 | 理由 |
|------|------|------|
| コンソールアクセス | 有効（パスワード + MFA） | ブラウザから操作 |
| MFA | 必須 | アカウント保護 |
| アクセスキー | **作らない** | EC2 操作はコンソールで完結。キーは漏洩リスクになるため必要時のみ発行 |

**権限（最小権限のカスタムポリシー）:**

EC2 の起動・停止・削除、Security Group、キーペアの管理に必要な操作のみを許可する。
以下のポリシーを作成してグループにアタッチする。

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "EC2ReadOnly",
      "Effect": "Allow",
      "Action": [
        "ec2:Describe*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "EC2ManageInstances",
      "Effect": "Allow",
      "Action": [
        "ec2:RunInstances",
        "ec2:StartInstances",
        "ec2:StopInstances",
        "ec2:TerminateInstances",
        "ec2:RebootInstances"
      ],
      "Resource": "*"
    },
    {
      "Sid": "EC2ManageNetworkAndKeys",
      "Effect": "Allow",
      "Action": [
        "ec2:CreateSecurityGroup",
        "ec2:DeleteSecurityGroup",
        "ec2:AuthorizeSecurityGroupIngress",
        "ec2:RevokeSecurityGroupIngress",
        "ec2:CreateKeyPair",
        "ec2:DeleteKeyPair",
        "ec2:CreateTags"
      ],
      "Resource": "*"
    }
  ]
}
```

- `ec2:Describe*` は読み取り専用でリソース指定不可のため `*` とする（AWS 仕様）
- 変更系は本プロジェクトで使う操作のみに限定
- さらに絞る場合はリージョン条件（`aws:RequestedRegion`）やタグ条件を追加できる

本プロジェクトは EC2 の操作だけで完結するため、CLI（aws コマンド）を使わないなら
アクセスキーは不要。CLI が必要になった時点で、必要な権限のキーを発行する。

### 想定コスト

| 項目 | 月額目安 |
|------|---------|
| EC2 t3.micro | 約 $8〜10 |
| EBS 8GB | 約 $0.8 |
| ネットワーク受信 | 無料 |
| ネットワーク送信 | ほぼ無料（100GB まで無料枠） |
| **合計** | **約 $10（約1,500円）** |

データ収集が終わったらインスタンスを停止すれば課金も止まる。

## デプロイ手順

### 1. EC2 インスタンスの起動

- AMI: Ubuntu Server 22.04 LTS
- インスタンスタイプ: t3.micro
- ストレージ: 8GB gp3
- キーペア: 新規作成してローカルに保存（管理 SSH 用）

### 2. Security Group の設定

**重要: ポートごとにアクセス範囲を厳密に分ける。**

| タイプ | ポート | ソース | 用途 |
|-------|-------|--------|------|
| Custom TCP | 2222 | 0.0.0.0/0 | SSH Honeypot（攻撃者に公開） |
| Custom TCP | 8080 | 0.0.0.0/0 | HTTP Honeypot（攻撃者に公開） |
| Custom TCP | 8000 | 自分の IP/32 | API（管理用） |
| Custom TCP | 3000 | 自分の IP/32 | Dashboard（管理用） |
| SSH | 22 | 自分の IP/32 | 管理 SSH（22番はHoneypotではない） |

**注意:**
- 管理 SSH は 22 番、Honeypot SSH は 2222 番。混同しないこと
- 8000 / 3000 / 22 は必ず自分の IP のみに制限する（全開放すると管理系が攻撃される）

### 3. サーバーへの初期セットアップ

管理 SSH でログイン後:

```bash
# システム更新
sudo apt update && sudo apt upgrade -y

# Docker インストール
sudo apt install -y docker.io docker-compose-v2
sudo systemctl enable --now docker

# 現在のユーザーを docker グループに追加
sudo usermod -aG docker $USER
# 再ログインして反映
exit
```

### 4. コードの配置

```bash
# リポジトリをクローン（または scp で転送）
git clone <リポジトリURL> honeywatch
cd honeywatch
```

Git 操作を避ける場合はローカルから scp で転送:

```bash
# ローカルマシンで実行
scp -i <キーペア>.pem -r ./honeywatch ubuntu@<EC2のIP>:~/
```

### 5. 環境変数の設定

```bash
cp .env.example .env
nano .env
```

**本番で必ず変更する項目:**

```bash
ENVIRONMENT=production
LOG_LEVEL=INFO

# API 認証情報は必ず強力なものに変更
API_AUTH_USER=<任意のユーザー名>
API_AUTH_PASSWORD=<強力なパスワード>

# DB パスワードも変更推奨
DB_PASSWORD=<強力なパスワード>
```

### 6. 起動

```bash
cd docker
docker compose up --build -d

# マイグレーション実行（001: attack_events テーブル、002: attack_type/severity カラム）
docker compose exec api alembic upgrade head

# 状態確認
docker compose ps
docker compose logs -f
```

新規デプロイの場合は上記のマイグレーションだけでよい（既存データがないため backfill は不要）。

すでに Phase 1 時代のデータが入った環境をアップグレードする場合のみ、
未分類イベントを遡って分類するために backfill を実行する:

```bash
# 既存の未分類イベントに attack_type / severity を付与する
docker compose exec worker python -m honeywatch.detection.backfill
```

### 7. 動作確認

```bash
# ヘルスチェック（EC2 内から）
curl http://localhost:8000/api/v1/health
```

Dashboard は SSH ポートフォワーディング経由でアクセスするのが安全:

```bash
# ローカルマシンで実行（3000 と 8000 をトンネル）
ssh -i <キーペア>.pem -L 3000:localhost:3000 -L 8000:localhost:8000 ubuntu@<EC2のIP>
```

その後ローカルブラウザで http://localhost:3000 を開く。

## 運用

### データ収集

デプロイ後は放置するだけで攻撃ログが貯まる。SSH ポートは数分以内に Brute Force を受け始める。

```bash
# 収集状況の確認
curl -u <user>:<pass> http://localhost:8000/api/v1/dashboard/summary

# 攻撃分類の確認（Phase 2）
curl -u <user>:<pass> "http://localhost:8000/api/v1/analysis/attack-types?period=24h"
curl -u <user>:<pass> "http://localhost:8000/api/v1/analysis/risk-ranking?period=24h"
```

Dashboard 下部の「Detection Analysis」セクションで、攻撃タイプ別集計・Severity 内訳・
Risk ランキングが確認できる。データが貯まってきたら `config/detection_rules.yaml` の
閾値を実際の攻撃分布に合わせて調整する。

### 停止・再開

```bash
# 停止（データは保持される）
docker compose down

# インスタンス自体を停止（課金を止める）
# → AWS コンソールから「インスタンスを停止」

# 再開
docker compose up -d
```

### ログのバックアップ

```bash
# PostgreSQL のダンプを取得
docker compose exec postgres pg_dump -U honeywatch honeywatch > backup_$(date +%Y%m%d).sql
```

## セキュリティチェックリスト

デプロイ前に確認する:

- [ ] Security Group で 8000 / 3000 / 22 を自分の IP のみに制限した
- [ ] `.env` の `API_AUTH_PASSWORD` を強力なものに変更した
- [ ] `.env` の `DB_PASSWORD` を変更した
- [ ] ルートアカウントに MFA を設定した
- [ ] 予算アラートを設定した
- [ ] Dashboard は直接公開せず SSH トンネル経由でアクセスする

## トラブルシューティング

| 症状 | 確認事項 |
|------|---------|
| Honeypot に接続できない | Security Group で 2222/8080 が開いているか |
| Dashboard が見れない | SSH トンネルが張れているか、8000/3000 が自分の IP で許可されているか |
| コンテナが起動しない | `docker compose logs <サービス名>` でエラー確認 |
| DB 接続エラー | `docker compose ps` で postgres が healthy か確認 |
