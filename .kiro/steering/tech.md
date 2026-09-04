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

## 実行環境（WSL）の注意

- プロジェクトは WSL（Ubuntu）上に配置されており、Kiro のコマンド実行は PowerShell を起点として `wsl -e bash -lc "..."` の形で WSL 内に渡される。
- この PowerShell → WSL の二重解釈により、クオート（特にシングルクオート）やセミコロンを含む複雑なコマンドは壊れやすい。Python の `python -c "..."` のようなインラインコードも失敗しやすい。
- 対策として、コマンドはできるだけ単一トークンのシンプルな形に分割して実行する。複数ステップが必要な場合はセミコロンや `&&` で繋がず、コマンドを分けて実行する。
- インラインコードで検証したい場合は、スクリプトをファイルに書き出してから `uv run python <file>` で実行する。
- パッケージの導入確認などは `uv pip list | grep -Ei "..."` のような単純なコマンドで代替する。

## コーディング規約

- Ruff を使ったリント・フォーマット
- mypy による型チェック（strict モード推奨）
- すべての関数・メソッドに型アノテーションを付ける
- docstring は Google スタイルで記述
- テストは pytest を使用し、`tests/` ディレクトリに配置
- 非同期処理は asyncio / async-await を基本とする
