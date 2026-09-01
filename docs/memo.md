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

### 初期に観測した攻撃

稼働開始から数時間以内に実際の攻撃を観測:

- zgrab による `/hudson` スキャン（Jenkins 系の脆弱性偵察, 送信元 172.202.121.211）
- python-requests による `/api/kernels` `/api/v1/version` への複数アクセス
  （Jupyter Notebook の脆弱性偵察, 送信元 3.74.226.174, 同一IPから4回）

いずれも HTTP Honeypot（8080）で観測。自動化されたインターネットスキャンボットによるもの。

### 補足

- API のタイムスタンプは UTC 記録（JST = UTC + 9時間）
- 例: ログの `2026-09-01T03:16 UTC` = JST 12:16
