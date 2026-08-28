# Tech Stack

## 言語

- Python 3.12+

## パッケージ管理

- uv（推奨）— 高速な Python パッケージマネージャー
- pyproject.toml でプロジェクト設定・依存関係を管理

## フレームワーク・ライブラリ

### バックエンド / API

| ライブラリ | 用途 |
|-----------|------|
| FastAPI | REST API サーバー（Dashboard 向け） |
| Uvicorn | ASGI サーバー |
| SQLAlchemy | ORM / データベースアクセス |
| Alembic | データベースマイグレーション |
| Pydantic | データバリデーション / スキーマ定義 |

### Honeypot

| ライブラリ | 用途 |
|-----------|------|
| asyncssh | SSH Honeypot 実装 |
| aiohttp | HTTP Honeypot 実装 |
| asyncio | 非同期イベントループ |

### データ処理・分析

| ライブラリ | 用途 |
|-----------|------|
| Redis | イベントキュー / キャッシュ |
| Celery | 非同期タスク（攻撃分類、アラート送信等） |

### フロントエンド（Dashboard）

| ライブラリ | 用途 |
|-----------|------|
| React | Dashboard UI |
| TypeScript | 型安全なフロントエンド開発 |
| Recharts or Chart.js | グラフ・可視化 |
| TailwindCSS | スタイリング |

### AI / セキュリティインテリジェンス（Phase 3-4）

| ライブラリ | 用途 |
|-----------|------|
| OpenAI API / LLM | 攻撃ログ要約・分析 |
| GeoIP2 (MaxMind) | IP ジオロケーション |

### 通知（Phase 3）

| ライブラリ | 用途 |
|-----------|------|
| httpx | Slack / Discord Webhook 通知 |

## データベース

- PostgreSQL — メインデータストア（攻撃ログ、分類結果、IP 分析）
- Redis — イベントキュー、キャッシュ、リアルタイム集計

## インフラ

- Docker / Docker Compose — ローカル開発・デプロイ
- Nginx — リバースプロキシ（本番時）

## コマンド

| 操作 | コマンド |
|------|---------|
| 依存インストール | `uv sync` |
| 開発サーバー起動（API） | `uv run uvicorn honeywatch.api.main:app --reload` |
| Honeypot 起動 | `uv run python -m honeywatch.honeypot` |
| マイグレーション実行 | `uv run alembic upgrade head` |
| マイグレーション作成 | `uv run alembic revision --autogenerate -m "description"` |
| テスト実行 | `uv run pytest` |
| リント | `uv run ruff check .` |
| フォーマット | `uv run ruff format .` |
| 型チェック | `uv run mypy .` |
| フロントエンド開発 | `cd frontend && npm run dev` |
| フロントエンドビルド | `cd frontend && npm run build` |

## コーディング規約

- Ruff を使ったリント・フォーマット
- mypy による型チェック（strict モード推奨）
- すべての関数・メソッドに型アノテーションを付ける
- docstring は Google スタイルで記述
- テストは pytest を使用し、`tests/` ディレクトリに配置
- 非同期処理は asyncio / async-await を基本とする
