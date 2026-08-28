# Project Structure

## ディレクトリ構成

```
honeywatch/
├── .kiro/                      # Kiro 設定
│   ├── steering/               # ステアリングルール
│   └── specs/                  # フィーチャー仕様
├── src/
│   └── honeywatch/             # Python メインパッケージ
│       ├── __init__.py
│       ├── honeypot/           # Honeypot 実装
│       │   ├── __init__.py
│       │   ├── ssh.py          # SSH Honeypot
│       │   ├── http.py         # HTTP Honeypot
│       │   └── base.py         # Honeypot 基底クラス
│       ├── collector/          # イベント収集・正規化
│       │   ├── __init__.py
│       │   ├── events.py       # イベントモデル定義
│       │   └── handler.py      # イベントハンドラー
│       ├── detection/          # 攻撃分類・パターン検出
│       │   ├── __init__.py
│       │   ├── classifier.py   # 攻撃タイプ分類
│       │   ├── patterns.py     # 攻撃パターン定義
│       │   └── mitre.py        # MITRE ATT&CK マッピング
│       ├── analysis/           # 分析ロジック
│       │   ├── __init__.py
│       │   ├── ip.py           # IP 分析・リスクスコア
│       │   ├── timeline.py     # タイムライン分析
│       │   └── geoip.py        # GeoIP ルックアップ
│       ├── alert/              # アラート通知
│       │   ├── __init__.py
│       │   ├── rules.py        # アラートルール定義
│       │   └── notifier.py     # 通知送信（Slack/Discord）
│       ├── ai/                 # AI 分析（Phase 4）
│       │   ├── __init__.py
│       │   └── analyst.py      # LLM ベースの攻撃要約
│       ├── api/                # FastAPI REST API
│       │   ├── __init__.py
│       │   ├── main.py         # FastAPI アプリケーション
│       │   ├── routes/         # エンドポイント定義
│       │   │   ├── __init__.py
│       │   │   ├── dashboard.py
│       │   │   ├── attacks.py
│       │   │   ├── ips.py
│       │   │   └── alerts.py
│       │   └── deps.py         # 依存性注入
│       ├── db/                 # データベース層
│       │   ├── __init__.py
│       │   ├── models.py       # SQLAlchemy モデル
│       │   ├── session.py      # DB セッション管理
│       │   └── repositories/   # リポジトリパターン
│       │       ├── __init__.py
│       │       ├── attack.py
│       │       └── ip.py
│       ├── core/               # 共通設定・ユーティリティ
│       │   ├── __init__.py
│       │   ├── config.py       # 環境設定
│       │   └── logging.py      # ロギング設定
│       └── tasks/              # Celery 非同期タスク
│           ├── __init__.py
│           └── workers.py
├── frontend/                   # React Dashboard
│   ├── package.json
│   ├── tsconfig.json
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/         # UI コンポーネント
│   │   ├── pages/              # ページコンポーネント
│   │   ├── hooks/              # カスタム React Hooks
│   │   ├── api/                # API クライアント
│   │   └── types/              # TypeScript 型定義
│   └── public/
├── migrations/                 # Alembic マイグレーション
│   ├── env.py
│   └── versions/
├── tests/                      # テスト
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_honeypot/
│   ├── test_collector/
│   ├── test_detection/
│   ├── test_analysis/
│   └── test_api/
├── docker/                     # Docker 関連
│   ├── Dockerfile
│   ├── Dockerfile.frontend
│   └── docker-compose.yml
├── docs/                       # プロジェクトドキュメント
├── pyproject.toml              # Python プロジェクト設定
├── alembic.ini                 # Alembic 設定
├── .env.example                # 環境変数テンプレート
├── .gitignore
└── README.md
```

## アーキテクチャ方針

### レイヤー構成

```
Honeypot → Collector → Detection → Database
                                       ↓
                            API → Dashboard
                                       ↓
                                  AI Analyst
```

- **Honeypot 層**: 攻撃トラフィックの受信・観測
- **Collector 層**: イベントの正規化・キューイング
- **Detection 層**: 攻撃分類・パターンマッチング
- **Database 層**: 永続化・クエリ
- **API 層**: Dashboard やクライアントへのデータ提供
- **AI 層**: 高レベルの分析・要約

### 設計原則

- 各層は疎結合に保ち、インターフェースを通じて連携する
- Honeypot と API は別プロセスとして起動できる設計にする
- ビジネスロジックはサービス層（detection, analysis）に集約し、API ルートは薄く保つ
- データベースアクセスはリポジトリパターンで抽象化する
- 設定は環境変数 + `core/config.py` で一元管理する

### 命名規則

- Python モジュール・変数: `snake_case`
- Python クラス: `PascalCase`
- React コンポーネント: `PascalCase`
- TypeScript 変数・関数: `camelCase`
- API エンドポイント: `kebab-case`（例: `/api/v1/attack-logs`）
- DB テーブル: `snake_case`（複数形、例: `attack_events`）
