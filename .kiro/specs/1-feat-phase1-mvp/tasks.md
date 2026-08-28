# Implementation Plan

## Overview

Phase 1 MVP の実装計画。Honeypot（SSH / HTTP）、イベント収集・保存基盤、REST API、Dashboard を構築する。インフラ基盤 → データ層 → Honeypot → API → フロントエンドの順序で実装し、最後に結合テストで全体の動作を確認する。

## Tasks

- [ ] 1. プロジェクト基盤セットアップ: pyproject.toml 作成、uv 仮想環境構築、`src/honeywatch/` パッケージ構造作成、`core/config.py`（pydantic-settings）、`core/logging.py`（JSON 構造化ログ）、`.env.example`、Ruff / mypy 設定
- [ ] 2. Docker Compose 環境構築: `docker/docker-compose.yml`（PostgreSQL / Redis）、`docker/Dockerfile`、ネットワーク分離（honeypot_net / internal_net）、ヘルスチェック追加、起動確認
- [ ] 3. データベース層の実装: `db/session.py`（SQLAlchemy async セッション）、`db/models.py`（AttackEventModel + インデックス）、Alembic 初期化・初期マイグレーション、`db/repositories/attack.py`（CRUD）
- [ ] 4. イベントキュー（Redis Stream）の実装: `collector/events.py`（AttackEvent / SSHEventData / HTTPEventData モデル）、`collector/handler.py`（EventQueue: publish / consume）、Consumer Group 管理、Redis 接続断リトライ
- [ ] 5. Event Worker の実装: `tasks/workers.py`（Redis Stream → PostgreSQL）、XREAD / ACK 処理、PostgreSQL 接続断再試行、エントリーポイント（`python -m honeywatch.worker`）、グレースフルシャットダウン
- [ ] 6. SSH Honeypot の実装: `honeypot/base.py`（BaseHoneypot 抽象クラス）、`honeypot/ssh.py`（asyncssh）、ホストキー自動生成・永続化、認証試行イベント記録、同時100接続対応・タイムアウト30秒、最大10回試行後切断、Redis 断時メモリバッファ
- [ ] 7. HTTP Honeypot の実装: `honeypot/http.py`（aiohttp）、パス別レスポンス戦略、レスポンスヘッダー偽装（Apache 模倣）、リクエスト情報イベント記録、Redis 断時メモリバッファ
- [ ] 8. Honeypot エントリーポイント: `honeypot/__main__.py`（一括起動）、シグナルハンドリング（SIGTERM / SIGINT）、クラッシュ時自動再起動、Docker Compose サービス追加
- [ ] 9. FastAPI REST API の実装: `api/main.py`、`api/deps.py`（DI・認証）、Basic Auth ミドルウェア、dashboard/summary・timeline・top-ips、events（ページネーション・フィルタ）、health（認証不要）、Docker Compose サービス追加
- [ ] 10. React Dashboard セットアップ: Vite + React + TypeScript、TailwindCSS（ダークテーマ）、API クライアント（Basic Auth 付き fetch）、型定義、Docker Compose サービス追加
- [ ] 11. Dashboard コンポーネント実装: Header / SummaryCard / AttackTimeline（Recharts） / TopIPsTable / ProtocolChart / RecentEventsTable、カスタム hooks、DashboardPage レイアウト、30秒自動ポーリング
- [ ] 12. 結合テスト・動作確認: Docker Compose 全サービス起動、SSH テスト接続 → DB 記録確認、HTTP テストリクエスト → DB 記録確認、Dashboard 表示確認、API 認証確認、README.md セットアップ手順記載

## Task Dependency Graph

```json
{
  "waves": [
    [1],
    [2, 3, 4],
    [5, 6, 7],
    [8, 9],
    [10],
    [11],
    [12]
  ]
}
```

## Notes

- Task 1 は全タスクの前提条件。最初に完了させる
- Task 3 と Task 4 は Task 1 完了後に並列実行可能
- Task 6 と Task 7 は Task 4 完了後に並列実行可能
- Task 10 と Task 11 は Task 9 完了後に順次実行
- Task 12 は他のすべてのタスクが完了してから実行する
- 各タスクの Docker Compose 関連サブタスクは、Task 2 で作成したファイルに追記する形で実施
