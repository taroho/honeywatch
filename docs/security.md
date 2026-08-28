# Security Design

## 概要

HoneyWatch は攻撃者に意図的にサービスをさらすため、通常のアプリケーション以上にセキュリティ設計が重要です。本ドキュメントでは、設計上のセキュリティ判断を記載します。

## 脅威モデル

| 脅威 | 対策 |
|------|------|
| Honeypot 経由で管理系に侵入 | ネットワーク分離（Honeypot → Redis のみ通信可能、DB/API に直接到達不可） |
| 攻撃者が Honeypot のプロセスを掌握 | 最小権限（非 root ユーザー）、コンテナ隔離 |
| DB 内のパスワードが漏洩 | 平文保存のリスクを認識した上で分析価値を優先。DB アクセス制御 + バックアップ暗号化で保護 |
| 管理 API への不正アクセス | Basic Auth + ポート公開を 127.0.0.1 限定 + 本番では IP 制限 |
| ログ内の個人情報（IP）の漏洩 | Dashboard は認証必須、DB は外部非公開 |

## 最小権限の原則

### コンテナ実行ユーザー

```dockerfile
RUN groupadd -r honeywatch && useradd -r -g honeywatch honeywatch
USER honeywatch
```

- Honeypot / API / Worker すべて非 root で実行
- コンテナ内でホスト側のファイルシステムにアクセス不可

### Honeypot の権限範囲

Honeypot コンテナができることは:
- 指定ポートで TCP 接続を受ける
- Redis Stream にイベントを XADD する

Honeypot コンテナができないことは:
- PostgreSQL に直接アクセス
- 他コンテナのファイルシステムにアクセス
- ホストネットワークへのアクセス

## ネットワーク分離

### Docker ネットワーク

| ネットワーク | 参加コンテナ | 用途 |
|------------|------------|------|
| honeypot_net | Honeypot | 外部からの攻撃トラフィック受信 |
| internal_net | 全コンテナ | 内部通信（Redis, DB, API） |

### ポート公開ポリシー

| サービス | バインドアドレス | 理由 |
|---------|----------------|------|
| SSH Honeypot | `0.0.0.0:2222` | 攻撃者に公開する必要がある |
| HTTP Honeypot | `0.0.0.0:8080` | 攻撃者に公開する必要がある |
| API | `127.0.0.1:8000` | 管理者のみアクセス |
| Dashboard | `127.0.0.1:3000` | 管理者のみアクセス |
| PostgreSQL | `127.0.0.1:5432` | 開発用。本番では公開しない |
| Redis | `127.0.0.1:6379` | 開発用。本番では公開しない |

### AWS デプロイ時の Security Group

```
Inbound:
  - 2222/tcp  : 0.0.0.0/0 (SSH Honeypot)
  - 8080/tcp  : 0.0.0.0/0 (HTTP Honeypot)
  - 8000/tcp  : 自分の IP/32 (API)
  - 3000/tcp  : 自分の IP/32 (Dashboard)
  - 22/tcp    : 自分の IP/32 (管理SSH)

Outbound:
  - All traffic : 0.0.0.0/0
```

## データ保護

### パスワードの取り扱い

攻撃者が試行したパスワードは**平文で保存**します。

```python
# 平文のまま記録（分析用途を優先）
ssh_data = SSHEventData(
    username=username,
    password=password,  # 平文
    ...
)
```

**判断根拠:**
- 辞書攻撃で使われるパスワードの傾向分析（Top パスワードランキング等）に平文が必要
- 攻撃者が使う辞書ファイルの特定に利用
- 先行 Honeypot プロジェクト（Cowrie, Kippo）は平文記録が標準

**リスク認識:**
- DB が漏洩した場合、パスワードリストとして悪用される可能性がある
- 攻撃者が誤って自身のパスワードを入力するケースがある

**対策:**
- DB は外部非公開（127.0.0.1 のみ）
- Dashboard / API は認証必須
- 本番環境では DB バックアップを暗号化
- 将来的に一定期間後のマスク処理を検討

### IP アドレスの取り扱い

IP アドレスは攻撃分析に不可欠なためそのまま保存しますが:
- Dashboard へのアクセスは認証必須
- DB は外部非公開
- 将来的に一定期間後の匿名化（上位ビットのマスク）を検討

## 認証

### API (Phase 1)

- HTTP Basic Auth（`Authorization: Basic <base64>` ヘッダー）
- タイミング攻撃対策: `secrets.compare_digest` を使用
- 認証情報は環境変数で設定（ハードコードしない）

### Phase 2 以降の計画

- JWT トークンベース認証に移行予定
- ログイン試行回数制限（Rate Limiting）
- セッション管理

## コンテナセキュリティ

| 対策 | 実装 |
|------|------|
| 非 root 実行 | Dockerfile で `USER honeywatch` |
| 軽量ベースイメージ | `python:3.12-slim`（攻撃面を最小化） |
| 不要パッケージ排除 | `--no-install-recommends` |
| restart policy | `unless-stopped`（クラッシュ時自動復旧） |
| read-only FS | 将来的に `read_only: true` を検討 |

## 既知のリスクと今後の対策

### ホスト侵害時のコンテナ隔離の限界

現在の構成では全コンポーネントが同一 EC2 上の Docker コンテナとして動作しています。Docker のプロセス隔離はネットワーク・ファイルシステムレベルの分離を提供しますが、**ホスト自体が root 権限で侵害された場合は全コンテナにアクセス可能**です。

**リスクシナリオ:**
- Honeypot のライブラリ（asyncssh, aiohttp）にリモートコード実行の脆弱性が発見される
- 攻撃者がコンテナ内で任意コードを実行 → コンテナエスケープ → ホスト権限取得
- DB 内の全ログデータ・API 認証情報が漏洩

**現時点で対策しない理由:**
- asyncssh / aiohttp でコンテナエスケープまで到達するには高度なエクスプロイトチェーンが必要
- Honeypot はユーザー入力を受けるだけで、任意コード実行の攻撃面が小さい
- EC2 2台 + VPC 分離の構成はコストが倍になり、個人プロジェクトの規模に見合わない

**本番環境で対策する場合:**
- Honeypot を別 EC2（別 VPC サブネット）に配置し、Redis のみ VPC Peering で接続
- Honeypot EC2 には DB / API へのネットワーク経路を一切持たせない
- ログ保管用 EC2 は Private Subnet に配置し、インターネットから直接到達不可にする
- Honeypot EC2 は定期的に破棄・再作成する（Immutable Infrastructure）
