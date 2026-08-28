# HoneyWatch

**Honeypot-Based Attack Monitoring & Analysis Platform**

インターネット上の不審なアクセスを Honeypot で観測し、攻撃パターンを分析・可視化するセキュリティ監視プラットフォーム。

## アーキテクチャ

```
                Internet
                   │
         ┌─────────▼─────────┐
         │     Honeypots     │
         │  SSH(:2222)       │
         │  HTTP(:8080)      │
         └─────────┬─────────┘
                   │
          ┌────────▼────────┐
          │  Redis Stream   │
          └────────┬────────┘
                   │
          ┌────────▼────────┐
          │  Event Worker   │
          └────────┬────────┘
                   │
          ┌────────▼────────┐
          │   PostgreSQL    │
          └────────┬────────┘
                   │
          ┌────────▼────────┐
          │  FastAPI (:8000)│
          └────────┬────────┘
                   │
          ┌────────▼────────┐
          │ Dashboard(:3000)│
          └─────────────────┘
```

## クイックスタート

### 前提条件

- Docker / Docker Compose
- Python 3.12+ / uv（ローカル開発時）
- Node.js 20+（フロントエンド開発時）

### 全サービス一括起動（Docker Compose）

```bash
# 環境変数ファイルを準備
cp .env.example .env

# 全サービスをビルド・起動
cd docker
docker compose up --build -d

# マイグレーション実行
docker compose exec api alembic upgrade head

# ログ確認
docker compose logs -f
```

起動後:
- Dashboard: http://localhost:3000
- API: http://localhost:8000/api/v1/health
- SSH Honeypot: localhost:2222
- HTTP Honeypot: http://localhost:8080

### ローカル開発（個別起動）

```bash
# Python 依存インストール
uv sync --extra dev

# PostgreSQL / Redis を起動（Docker）
cd docker
docker compose up -d postgres redis

# マイグレーション実行
uv run alembic upgrade head

# API サーバー起動
uv run uvicorn honeywatch.api.main:app --reload

# Honeypot 起動（別ターミナル）
uv run python -m honeywatch.honeypot

# Worker 起動（別ターミナル）
uv run python -m honeywatch.worker

# フロントエンド起動（別ターミナル）
cd frontend
npm install
npm run dev
```

## テスト接続

### SSH Honeypot テスト

```bash
# SSH 接続を試行（常に認証失敗する）
ssh -p 2222 test@localhost
```

### HTTP Honeypot テスト

```bash
# 各種パスへリクエスト
curl http://localhost:8080/
curl http://localhost:8080/admin
curl http://localhost:8080/api/users
curl http://localhost:8080/wp-login.php
```

### API テスト

```bash
# ヘルスチェック（認証不要）
curl http://localhost:8000/api/v1/health

# サマリー（Basic Auth 必須）
curl -u admin:changeme http://localhost:8000/api/v1/dashboard/summary

# イベント一覧
curl -u admin:changeme http://localhost:8000/api/v1/events

# タイムライン
curl -u admin:changeme "http://localhost:8000/api/v1/dashboard/timeline?period=24h&interval=1h"
```

## コマンド一覧

| 操作 | コマンド |
|------|---------|
| 依存インストール | `uv sync --extra dev` |
| API 起動 | `uv run uvicorn honeywatch.api.main:app --reload` |
| Honeypot 起動 | `uv run python -m honeywatch.honeypot` |
| Worker 起動 | `uv run python -m honeywatch.worker` |
| マイグレーション実行 | `uv run alembic upgrade head` |
| マイグレーション作成 | `uv run alembic revision --autogenerate -m "description"` |
| テスト | `uv run pytest` |
| リント | `uv run ruff check .` |
| フォーマット | `uv run ruff format .` |
| 型チェック | `uv run mypy src/` |
| フロントエンド開発 | `cd frontend && npm run dev` |
| フロントエンドビルド | `cd frontend && npm run build` |

## 環境変数

`.env.example` を参照。主な設定:

| 変数 | 説明 | デフォルト |
|------|------|-----------|
| `ENVIRONMENT` | 環境名 | development |
| `LOG_LEVEL` | ログレベル | INFO |
| `DB_HOST` | PostgreSQL ホスト | localhost |
| `DB_PASSWORD` | DB パスワード | honeywatch |
| `REDIS_HOST` | Redis ホスト | localhost |
| `HONEYPOT_SSH_PORT` | SSH Honeypot ポート | 2222 |
| `HONEYPOT_HTTP_PORT` | HTTP Honeypot ポート | 8080 |
| `API_AUTH_USER` | API 認証ユーザー | admin |
| `API_AUTH_PASSWORD` | API 認証パスワード | changeme |

## セキュリティ注意事項

- **本番デプロイ時は必ず `API_AUTH_PASSWORD` を変更してください**
- Honeypot は意図的に外部公開しますが、管理ポート（API / Dashboard）は IP 制限をかけてください
- パスワードは SHA-256 ハッシュとして保存されます（平文保存なし）
- Security Group で Honeypot ポートのみ全開放、管理ポートは自分の IP のみ許可

## プロジェクト構成

```
honeywatch/
├── src/honeywatch/       # Python バックエンド
│   ├── api/              # FastAPI REST API
│   ├── collector/        # イベント収集・Redis Stream
│   ├── core/             # 設定・ログ
│   ├── db/               # SQLAlchemy / Repository
│   ├── honeypot/         # SSH / HTTP Honeypot
│   └── tasks/            # Event Worker
├── frontend/             # React Dashboard
├── docker/               # Docker Compose / Dockerfile
├── migrations/           # Alembic マイグレーション
└── tests/                # pytest テスト
```