# 開発メモ

## Phase 2 完了時点の状態（2026-08-31）

Phase 2（Detection）の Task 1〜12 を実装・動作確認済み:

- DB スキーマ拡張（attack_type / severity）、マイグレーション 002 適用済み
- 攻撃分類エンジン（6タイプ）、Severity 判定、Risk Score
- Worker への分類統合、backfill による既存データ再分類
- 分析 API（/api/v1/analysis/*）
- Dashboard に Detection Analysis セクション追加
- ユニットテスト 32件（分類・Severity・RiskScorer・ルールローダー）

## 次にやること

### AWS デプロイ（家の PC でパスキーが必要）

`docs/deployment.md` に従って EC2 にデプロイし、実際の攻撃データを収集する。
データが貯まったら `config/detection_rules.yaml` の閾値を実分布に合わせて調整する。

### 閾値チューニングの観点

- brute_force の min_attempts が実際のボット攻撃に対して適切か
- port_scan の min_distinct_ports（現状3）が妥当か
- Severity 判定が実データで偏りすぎないか（HIGH ばかり / LOW ばかりになっていないか）

## 運用記録（AWS デプロイ）

### 稼働開始

- 2026/09/01 12:15 (JST) 本番稼働開始（AWS EC2, ap-southeast-2 シドニー）
- インスタンス: t3.micro / EBS 16GB / スワップ 2GB
- 全6コンテナ稼働（postgres / redis / api / worker / honeypot / frontend）
- 2026/09/01 15:35 (JST) Elastic IP を割り当て

### 初期に観測した攻撃

稼働開始から数時間以内に実際の攻撃を観測:

- zgrab による `/hudson` スキャン（Jenkins 系の脆弱性偵察, 送信元 172.202.121.211）
- python-requests による `/api/kernels` `/api/v1/version` への複数アクセス
  （Jupyter Notebook の脆弱性偵察, 送信元 3.74.226.174, 同一IPから4回）

いずれも HTTP Honeypot（8080）で観測。自動化されたインターネットスキャンボットによるもの。

### 補足

- API のタイムスタンプは UTC 記録（JST = UTC + 9時間）
- 例: ログの `2026-09-01T03:16 UTC` = JST 12:16

## 管理 SSH を 5555 に移動し 22番を Honeypot へ

SSH 攻撃を観測するため、22番を SSH Honeypot に明け渡す。
管理用 SSH（OS の sshd）は 5555番に移動する（SSM は使わず SSH 継続）。

### 変更点

- docker-compose.yml: Honeypot の SSH を `0.0.0.0:22:2222`（ホスト22 → コンテナ2222）に変更
- EC2 の /etc/ssh/sshd_config: `Port 5555` に変更（管理 SSH を移動）
- Security Group: 22番を `0.0.0.0/0` に全開放、5555番を自分の IP のみで許可

### 移行手順（締め出し防止のため順番厳守）

1. sshd_config に `Port 22` と `Port 5555` を両方書いて再起動（両方で入れる状態に）
2. Security Group に 5555番（自IP）を追加
3. `ssh -p 5555` で入れることを確認（ここで入れないまま進むと締め出される）
4. sshd_config から `Port 22` を削除して 5555 のみにし、再起動
5. コード反映（docker compose up -d honeypot）
6. Security Group で 22番を 0.0.0.0/0 に変更

### 注意点

- Honeypot コンテナは非 root 実行のため 22番を直接バインドできない。
  そのためホスト22 → コンテナ2222 のポートマッピングにしている。
- destination_port は `HONEYPOT_SSH_PUBLIC_PORT=22` を設定することで 22 として記録される
  （リッスンは 2222、記録は 22 に分離。config の ssh_reported_port プロパティで実現）。
- 管理接続コマンドは `ssh -p 5555 -i <キー>.pem ubuntu@<IP>` になる。
- Dashboard 閲覧の SSH トンネルも 5555 経由になる:
  `ssh -p 5555 -i <キー>.pem -L 3000:localhost:3000 -L 8000:localhost:8000 ubuntu@<IP>`
