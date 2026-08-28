# Design

## Overview

Phase 1 MVP では HoneyWatch の基盤を構築する。Honeypot（SSH / HTTP）で攻撃トラフィックを観測し、Redis Stream 経由でイベントを収集・正規化し、PostgreSQL に永続化する。FastAPI で REST API を提供し、React Dashboard で攻撃状況を可視化する。

### 設計方針

- 各コンポーネントは独立したプロセスとして動作し、Redis を介して疎結合に連携する
- Honeypot と管理系（API / Dashboard）はネットワークレベルで分離する
- 非同期処理を基本とし、大量の同時接続を効率的に処理する
- データモデルは拡張性を考慮し、Phase 2 以降の攻撃分類・IP 分析に対応できる構造にする

## Architecture

### システム構成図

```
                    Internet
                       │
             ┌─────────▼─────────┐
             │     Honeypots     │
             │  (SSH / HTTP)     │
             │  Port 2222/8080   │
             └─────────┬─────────┘
                       │ イベント発行
                       ▼
              ┌─────────────────┐
              │  Event Queue    │
              │  (Redis Stream) │
              └────────┬────────┘
                       │ consume
                       ▼
              ┌─────────────────┐
              │  Event Worker   │
              │  (正規化+保存)   │
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │  PostgreSQL     │
              │  (攻撃ログDB)   │
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │  FastAPI        │
              │  (REST API)     │
              └────────┬────────┘
                       │
                       ▼
              ┌─────────────────┐
              │  React Dashboard│
              │  (フロントエンド) │
              └─────────────────┘
```

### プロセス構成

| プロセス | 役割 | ポート |
|---------|------|--------|
| SSH Honeypot | SSH 接続の観測 | 2222 |
| HTTP Honeypot | HTTP リクエストの観測 | 8080 |
| Event Worker | Redis → PostgreSQL への永続化 | - |
| FastAPI Server | Dashboard 向け REST API | 8000 |
| React Dev Server | Dashboard UI（開発時） | 3000 |
| Redis | イベントキュー / キャッシュ | 6379 |
| PostgreSQL | 攻撃ログ永続化 | 5432 |

### ネットワーク分離

- Honeypot は外部ネットワークに公開する（`0.0.0.0` バインド）
- API / Dashboard は管理用ネットワークのみに公開する（`127.0.0.1` または Docker 内部ネットワーク）
- Redis / PostgreSQL は外部に公開しない（Docker 内部ネットワークのみ）

### イベントフロー

1. Honeypot が接続/リクエストを受信
2. Honeypot が `AttackEvent` を生成し、Redis Stream に XADD
3. Event Worker が Redis Stream から XREAD（Consumer Group）
4. Worker がイベントを正規化し PostgreSQL に INSERT
5. Dashboard が FastAPI 経由でデータを取得・表示

## Components and Interfaces

| コンポーネント | 責務 | 公開インターフェース |
|--------------|------|-------------------|
| SSH Honeypot | SSH 接続の観測・イベント発行 | TCP :2222（外部公開） |
| HTTP Honeypot | HTTP リクエストの観測・イベント発行 | TCP :8080（外部公開） |
| Event Queue (Redis Stream) | Honeypot → Worker 間のイベント中継 | Stream: `honeywatch:events` |
| Event Worker | イベント正規化・DB 永続化 | なし（内部プロセス） |
| FastAPI Server | Dashboard 向け REST API 提供 | HTTP :8000（管理用） |
| React Dashboard | 攻撃データの可視化 UI | HTTP :3000（管理用） |
| PostgreSQL | 攻撃ログ永続化 | TCP :5432（内部のみ） |
| Redis | イベントキュー・キャッシュ | TCP :6379（内部のみ） |

### コンポーネント間通信

- Honeypot → Redis: `XADD` でイベントを投入
- Worker → Redis: `XREADGROUP` でイベントを消費、処理後 `XACK`
- Worker → PostgreSQL: SQLAlchemy async で INSERT
- FastAPI → PostgreSQL: SQLAlchemy async で SELECT
- Dashboard → FastAPI: HTTP REST（Basic Auth 付き）

## Data Models

### イベント共通スキーマ（Pydantic）

```python
class AttackEvent(BaseModel):
    """Honeypot が生成する攻撃イベントの共通フォーマット"""
    id: UUID
    timestamp: datetime
    source_ip: str
    source_port: int
    destination_port: int
    protocol: Literal["ssh", "http"]
    event_type: str  # "ssh_login_attempt", "http_request" など
    raw_data: dict   # プロトコル固有のデータ
```

### SSH イベント raw_data

```python
class SSHEventData(BaseModel):
    """SSH Honeypot 固有のイベントデータ"""
    username: str
    password: str           # 平文（攻撃パターン分析用）
    client_version: str     # SSH クライアントバージョン
    connection_duration: float  # 秒
    auth_success: bool      # 常に False
```

### HTTP イベント raw_data

```python
class HTTPEventData(BaseModel):
    """HTTP Honeypot 固有のイベントデータ"""
    method: str             # GET, POST, PUT 等
    path: str
    headers: dict[str, str]
    user_agent: str
    body_preview: str | None  # 先頭 1024 バイトのみ
    status_code: int        # 返したレスポンスコード
```

### データベーステーブル（SQLAlchemy）

```python
class AttackEventModel(Base):
    __tablename__ = "attack_events"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(index=True)
    source_ip: Mapped[str] = mapped_column(String(45), index=True)  # IPv6 対応
    source_port: Mapped[int]
    destination_port: Mapped[int]
    protocol: Mapped[str] = mapped_column(String(10), index=True)
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    raw_data: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
```

### インデックス戦略

| カラム | インデックス種類 | 用途 |
|--------|----------------|------|
| timestamp | B-tree | タイムライン検索、範囲クエリ |
| source_ip | B-tree | IP 別検索、Top IP 集計 |
| protocol | B-tree | プロトコル別フィルタ |
| event_type | B-tree | イベントタイプ別フィルタ |
| (timestamp, protocol) | 複合 | タイムライン + プロトコル別表示 |

### Redis Stream 構造

```
Stream Key: honeywatch:events

Entry:
  id: <auto>
  data: {
    "event_json": "<AttackEvent の JSON 文字列>"
  }

Consumer Group: honeywatch-workers
Consumer: worker-1
```

## API Endpoints

### Base URL

```
/api/v1
```

### GET /api/v1/dashboard/summary

Dashboard サマリーカード用の統計データを返す。

**Response:**
```json
{
  "attacks_today": 1284,
  "unique_ips_today": 237,
  "ssh_attempts_today": 934,
  "http_attacks_today": 217,
  "period_start": "2026-08-28T00:00:00Z",
  "period_end": "2026-08-28T23:59:59Z"
}
```

### GET /api/v1/dashboard/timeline

時間帯別の攻撃数を返す（タイムライングラフ用）。

**Query Parameters:**
| パラメータ | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| period | string | "24h" | 集計期間（1h, 6h, 24h, 7d） |
| interval | string | "1h" | 集計間隔（5m, 15m, 1h） |

### GET /api/v1/dashboard/top-ips

攻撃数の多い送信元 IP ランキングを返す。

**Query Parameters:**
| パラメータ | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| limit | int | 10 | 取得件数 |
| period | string | "24h" | 集計期間 |

### GET /api/v1/events

攻撃イベント一覧を返す（ページネーション付き）。

**Query Parameters:**
| パラメータ | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| page | int | 1 | ページ番号 |
| per_page | int | 50 | 1ページあたりの件数（最大100） |
| protocol | string | null | フィルタ: ssh, http |
| source_ip | string | null | フィルタ: 送信元 IP |
| since | datetime | null | フィルタ: 開始日時 |
| until | datetime | null | フィルタ: 終了日時 |

### GET /api/v1/health

ヘルスチェック用エンドポイント（認証不要）。

### 認証

Phase 1 では Basic Auth を使用する。

- `Authorization: Basic <base64(username:password)>` ヘッダーが必要
- 認証情報は環境変数 `API_AUTH_USER` / `API_AUTH_PASSWORD` で設定
- `/api/v1/health` のみ認証不要

## Honeypot Design

### 共通設計 — BaseHoneypot 抽象クラス

すべての Honeypot は `BaseHoneypot` を継承し、以下のインターフェースを実装する:

```python
class BaseHoneypot(ABC):
    """Honeypot の基底クラス"""

    def __init__(self, event_queue: EventQueue):
        ...

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    async def emit_event(self, event: AttackEvent) -> None:
        """イベントをキューに送信する（Redis 断時はメモリバッファに保持）"""
        ...
```

### SSH Honeypot

- asyncssh を使用して SSH サーバーを実装
- 認証は常に失敗させる（任意のユーザー名/パスワードを受け付けて拒否）
- 接続ごとに記録: 送信元 IP/ポート、ユーザー名、パスワード SHA-256 ハッシュ、クライアントバージョン、接続時間
- 1 接続あたり最大 10 回の認証試行を許可し、その後切断
- 接続タイムアウト: 30 秒
- ホストキー: 初回起動時に RSA / Ed25519 キーを自動生成し `data/ssh_host_keys/` に永続化

### HTTP Honeypot

- aiohttp を使用して HTTP サーバーを実装
- Apache を模したレスポンスヘッダー（`Server: Apache/2.4.41 (Ubuntu)`）
- 記録: 送信元 IP/ポート、メソッド、パス、ヘッダー、User-Agent、ボディ先頭 1024 バイト

### レスポンス戦略

| パス | レスポンス |
|------|-----------|
| `/` | 200 + 簡易 HTML ページ |
| `/robots.txt` | 200 + 一般的な robots.txt |
| `/admin`, `/wp-admin`, `/login` | 401 + ログインフォーム風 HTML |
| `/api/*` | 403 + JSON エラー |
| その他 | 404 + 標準エラーページ |

## UI Layout

### 画面構成

```
┌─────────────────────────────────────────────────────┐
│  Header: HoneyWatch ロゴ + 最終更新時刻              │
├─────────────────────────────────────────────────────┤
│  [Attacks Today] [Unique IPs] [SSH Attempts] [HTTP] │
├─────────────────────────────────────────────────────┤
│  Attack Timeline（折れ線グラフ: 合計/SSH/HTTP 色分け）│
├──────────────────────────┬──────────────────────────┤
│  Top Source IPs          │  Protocol Distribution   │
│  （テーブル形式）          │  （ドーナツグラフ）       │
├──────────────────────────┴──────────────────────────┤
│  Recent Events（テーブル: Time, IP, Port, Protocol） │
└─────────────────────────────────────────────────────┘
```

### カラーテーマ（ダークテーマ）

- 背景: #0f172a / カード: #1e293b / アクセント: #3b82f6
- SSH: #f59e0b / HTTP: #10b981 / 危険: #ef4444

### データ更新

- 30 秒間隔で自動ポーリング（Phase 1）

## Error Handling

| 障害シナリオ | 対処 |
|------------|------|
| Redis 接続断 | Honeypot はメモリ内バッファに一時保持し、再接続後に flush |
| PostgreSQL 接続断 | Worker は Redis 内にイベントを未 ACK のまま保持し、復旧後に再処理 |
| Honeypot クラッシュ | Docker restart policy (`unless-stopped`) で自動再起動 |
| Worker クラッシュ | Docker restart policy で自動再起動。未 ACK イベントは Redis に残存 |
| API 認証失敗 | 401 Unauthorized を返す。ログに記録 |
| 不正なイベントデータ | Worker が Pydantic バリデーションでリジェクトし、エラーログに記録。Dead Letter 扱い |

## Testing Strategy

| レイヤー | テスト手法 | ツール |
|---------|-----------|--------|
| Honeypot | ユニットテスト（イベント生成ロジック） | pytest + asyncio |
| Event Queue | 結合テスト（Redis Stream publish/consume） | pytest + testcontainers |
| Worker | 結合テスト（Redis → PostgreSQL 永続化） | pytest + testcontainers |
| API | ユニットテスト + 結合テスト | pytest + httpx (TestClient) |
| Dashboard | コンポーネントテスト | Vitest + React Testing Library |
| E2E | Docker Compose 起動 → テスト接続 → DB 確認 | pytest + Docker Compose |

## Correctness Properties

- Honeypot は実際のシステムへの認証を許可しない（SSH は常に拒否、HTTP は模擬レスポンスのみ）
- パスワードは平文で保存する（攻撃パターン分析・辞書攻撃傾向の可視化に使用。リスクを認識した上で分析価値を優先）
- Redis 接続断時にイベントが消失しない（メモリバッファで一時保持）
- PostgreSQL 接続断時にイベントが消失しない（Redis 内に未 ACK として保持）
- API は認証なしではアクセスできない（health エンドポイント除く）
- Honeypot ポートと管理用ポートは異なるインターフェースにバインドされる
