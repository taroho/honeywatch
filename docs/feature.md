# 構想メモ（Feature Backlog）

まだ実装に着手していない「やりたいこと」の構想を記録するドキュメント。
実装フェーズに入る段階で `.kiro/specs/` 配下の正式な spec（requirements → design → tasks）に起こす。

---

## 複数 Honeypot EC2 + RDS 集約構成

### 背景・目的

将来的に、別の EC2 上で SSH 認証を（限定的に）成功させ、
攻撃者が認証突破後に実行するコマンドを計測・記録したい。

これにより現行の「認証試行の観測」に加えて、
「認証突破後の挙動（実行コマンド）」まで観測範囲を広げる。

Honeypot が複数 EC2 に分散するため、各 EC2 ローカルの PostgreSQL では
イベントが分散してしまう。Dashboard / API から横断的に分析・可視化するために、
DB を単一の共有 RDS(PostgreSQL) に集約する。

### 目指す構成（案）

```
Honeypot EC2 A（現行: HTTP :8080 / SSH :22・隔離）
Honeypot EC2 B（新規: SSH 認証突破後のコマンド計測・隔離）
        │
        │ イベント送信（一方向・DB 資格情報は持たせない）
        ▼
    中継（Redis Stream / SQS / API ingest のいずれか）
        │
        ▼
分析・Dashboard EC2（管理系）
   ├── Event Worker（分類・正規化）
   ├── FastAPI API + Dashboard
   └──→ RDS (PostgreSQL) 共有DB   ← ここに集約する
```

- 現行の「EC2 1台同居 + ローカル PostgreSQL」から、
  DB の実体を RDS に切り出し、Dashboard / API は RDS を参照する。
- Honeypot EC2 は「イベントを送るだけ」。DB へ直接書き込ませない。

### 設計方針・論点

#### なぜ RDS に寄せるか

- 複数 Honeypot EC2 のイベントを 1 箇所に集約し、プロトコル横断で分析できる
  （同一 IP が SSH と HTTP の両方を叩いた、といった相関が見える）。
- Dashboard / API が参照する DB を 1 つに固定でき、分析ロジックを二重に持たなくて済む。
- バックアップ・冗長化・パッチ適用を RDS(マネージド) に任せられる。
- Honeypot 側の侵害から DB 本体を切り離せる。

#### セキュリティ（最重要）

product.md / architecture.md のセキュリティ方針（管理系と Honeypot 系の分離）を維持する。

- Honeypot EC2、特に SSH 認証突破を許す EC2 B は「侵入される前提の箱」。
  ここに RDS の資格情報を置かない。攻撃者にシェルを与える前提のため、
  資格情報奪取 → 共有 DB 到達のリスクを排除する。
- Honeypot → 分析系は中継（Redis / SQS / API ingest）を経由する一方向経路にする。
- RDS はプライベートサブネットに配置し、パブリックアクセス無効。
- Security Group は「分析系 EC2 からのみ 5432 を許可」。Honeypot EC2 からは接続不可。

#### 接続情報・認証情報の管理

現状の接続設定を確認した結果、RDS 切り替えは環境変数の差し替えだけで対応可能な作りになっている。

- `core/config.py` の `DatabaseSettings`（`DB_` プレフィックス）で
  `host` / `port` / `user` / `password` / `name` を個別に環境変数で上書きできる。
- `async_url` プロパティが `postgresql+asyncpg://...` を組み立て、
  `db/session.py` の `init_db()` はデフォルトで `settings.db.async_url` を使う。
  接続文字列がコードに直書きされていないため、`DB_HOST` を RDS エンドポイント、
  `DB_USER` / `DB_PASSWORD` / `DB_NAME` を RDS のものに差し替えれば切り替わる。
- RDS のパスワードを `.env` に平文で持つより、将来的には
  AWS Secrets Manager / SSM パラメータストアへ寄せる。

RDS 移行時に対応が必要な点（現状の作りでは未対応）:

- **SSL/TLS 接続**: RDS は SSL 接続が推奨（本番では強制も可能）。
  現状 `async_url` に SSL パラメータを渡す口がないため、
  asyncpg への `ssl` 指定（`create_async_engine` の `connect_args` 等）を追加する必要がある。
- **接続文字列一本での上書き口**: 現状は `DB_HOST` 等の個別指定のみ。
  `DATABASE_URL` 一本で上書きする経路は環境変数からは無い
  （`init_db(database_url=...)` にコードから直接渡す経路はある）。
  必要なら `DATABASE_URL` を優先する口を足すと運用が楽になる。

#### マイグレーション

- Alembic を利用中のため、RDS に対して `alembic upgrade head` で同一スキーマを再現できる。
- 既存データの移行は `pg_dump`（現行 EC2 ローカル DB）→ RDS へ `restore` の流れ。

### 未決事項（次に詰める）

1. Honeypot EC2 → 分析系への経路：Redis 直か / SQS か / API ingest エンドポイントか。
2. 共有 DB：RDS にするか / 分析系 EC2 同居の自前 PostgreSQL にするか（現状は RDS 方針）。
3. SSH コマンド計測イベントを、既存 `attack_events` スキーマに乗せるか、
   専用テーブル / カラムを追加するか。
4. 現行の DB 接続設定が環境変数だけで RDS に切り替え可能か（`core/config.py` の確認）。
   → 確認済み。`DB_*` 環境変数の差し替えで切り替え可能。
   ただし RDS の SSL 接続対応と、必要なら `DATABASE_URL` 一本での上書き口の追加が残課題。

### EC2 台数の考え方（トレードオフ）

上の構成図は「最大分離」に振ると EC2 3 台（Honeypot A / Honeypot B / 管理系）+ RDS になる。
ただし 3 台は必須ではなく、台数はコストと分離要件のトレードオフ。RDS はマネージドのため
EC2 の台数計算には含めない。

| パターン | EC2 台数 | 内容 | 備考 |
|---------|---------|------|------|
| 最大分離 | 3 台 + RDS | Honeypot A / Honeypot B / 管理系 を全て別 EC2 | 分離最強・コスト最大。ポートフォリオには過剰気味 |
| Honeypot 集約 | 2 台 + RDS | Honeypot A+B を 1 台に同居 / 管理系 1 台 | コスト抑制と分離のバランス |
| 最小 | 1 台 + RDS | 現行 1 台同居のまま DB だけ RDS 化 | 一番安い。複数 Honeypot 集約の狙いは未実現 |

現実的な段階論:

1. 今: 1 台同居（現行）。
2. RDS 集約を試す: 管理系 1 台 + RDS（Honeypot はまだ 1 台）。
3. SSH 突破コマンド計測を足す: EC2 B を「シェルを与える高リスクな箱」として分離
   → ここで初めて 2〜3 台構成になる。

方針: 「3 台が必要」ではなく「SSH 突破という高リスク機能を足すなら、その箱だけ分ける」。
管理系は現行 EC2 を流用し、postgres コンテナを RDS 接続へ置き換えるのが素直。
現行 6 コンテナ（postgres / redis / api / worker / honeypot / frontend）のうち、
postgres を RDS に外出しし、honeypot の分離は任意。

### コード実装の置き場所（SSH 突破後のコマンド計測）

既存の SSH Honeypot（`honeypot/ssh.py`）は「認証を常に失敗させる」設計
（`validate_password` が常に False）。コマンド計測はこの挙動を壊さないよう、
**疑似シェル Honeypot を別ファイルで新設**する。structure.md の疎結合原則にも沿う。

| 内容 | 置き場所 | 新規/追記 |
|------|---------|-----------|
| 疑似シェル SSH サーバー | `honeypot/ssh_shell.py` | 新規（既存 `ssh.py` は温存） |
| コマンドイベントモデル | `collector/events.py`（例: `SSHCommandEventData`） | 追記 |
| コマンド分類（任意・後続） | `detection/classifier.py` | 追記 |
| 起動切り替え | `honeypot/__init__.py` + docker | 追記 |
| DB スキーマ（必要なら） | `db/models.py` + `migrations/` | 追記 |

ポイント:

- 認証を限定的に成功させ、`asyncssh.create_server` の `process_factory` に疑似シェルを差し込む
  （現行 `ssh.py` は `process_factory=None`。ここが差し込み口）。
- 共通部分（ホストキー生成・flush ループ）は `base.py` を継承して再利用。
- `AttackEvent` はそのまま流用し、`event_type="ssh_command"` を追加する形で
  既存の Redis Stream → Worker → DB フローに乗せられる（`protocol` は `ssh` のまま）。
- 実装着手時は正式 spec（例: `.kiro/specs/{連番}-feat-ssh-command-capture`）を切る。

### デプロイで「混ざらない」ための分離方針

現行は EC2 で `git pull` → `docker compose up` で全サービスが起動する運用。
同一リポジトリを 1 台目・2 台目で共有しても **コードは混ざらない**（`ssh.py` と
`ssh_shell.py` は別ファイル）。ただし何も工夫しないと **両 EC2 で全コンテナが
起動してしまう**（混ざるのはコードではなく「動くコンテナ」）。

対策: 同一リポジトリ・pull 運用は維持したまま、起動対象だけ役割ごとに分ける。

- **採用候補（おすすめ）**: docker-compose の `profiles` で役割を分ける。

  ```
  # 1台目（管理系）
  docker compose --profile management up -d
  # 2台目（疑似シェル Honeypot）
  docker compose --profile honeypot-shell up -d
  ```

  1 ファイルで管理でき pull は共通、起動コマンドで役割を振り分ける。
- 代替案: 役割別の compose 上書きファイル（`docker-compose.honeypot.yml` 等）に分割 /
  起動時にサービス名を明示指定（最小変更だが指定漏れリスクあり）。
- 役割ごとに `.env` を分け、2 台目は Redis / イベント送信先を 1 台目（管理系・中継）に向ける。

### 関連

- architecture.md「今後の拡張ポイント」Phase 4「SSH 疑似シェル（認証を限定的に成功させ、コマンド入力を記録）」の具体化にあたる。
