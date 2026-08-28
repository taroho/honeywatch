# Architecture

## 概要

HoneyWatch は Honeypot で攻撃を観測し、イベントとして収集・永続化し、Dashboard で可視化するプラットフォームです。

本ドキュメントでは、システムの全体構成と各設計判断の根拠を説明します。

## システム構成

```
                    Internet
                       │
             ┌─────────▼─────────┐
             │     Honeypots     │
             │  SSH (:2222)      │
             │  HTTP (:8080)     │
             └─────────┬─────────┘
                       │ XADD
                       ▼
              ┌─────────────────┐
              │  Redis Stream   │
              └────────┬────────┘
                       │ XREADGROUP
                       ▼
              ┌─────────────────┐
              │  Event Worker   │
              └────────┬────────┘
                       │ INSERT
                       ▼
              ┌─────────────────┐
              │  PostgreSQL     │
              └────────┬────────┘
                       │ SELECT
                       ▼
              ┌─────────────────┐
              │  FastAPI API    │
              └────────┬────────┘
                       │ HTTP
                       ▼
              ┌─────────────────┐
              │  Dashboard      │
              └─────────────────┘
```

## 設計判断とその根拠

### なぜ Honeypot と API を分離したか

Honeypot は攻撃者に直接さらすコンポーネントです。万が一脆弱性を突かれても、管理系（API / Dashboard / DB）に到達させないために、プロセスレベルとネットワークレベルの両方で分離しています。

- プロセス分離: Honeypot のクラッシュが API に影響しない
- ネットワーク分離: Docker ネットワークで Honeypot と管理系を別セグメントに配置
- 本番では Security Group で追加の制御を行う

### なぜ Redis Stream を中間キューにしたか

Honeypot から直接 DB に書くと:

1. DB 障害時にイベントが消失する
2. 大量アクセス時に DB がボトルネックになる
3. Honeypot プロセスが DB 接続の責任を持つことになり複雑化する

Redis Stream を挟むことで:

- **耐障害性**: DB ダウン中もイベントは Redis に蓄積され、復旧後に再処理される
- **バッファリング**: 攻撃のバースト時も Honeypot はブロックされない
- **責務の分離**: Honeypot は「観測して投入するだけ」、Worker は「保存するだけ」

Consumer Group により将来的な Worker スケールアウトにも対応しています。

### なぜ Honeypot にメモリバッファを持たせたか

Redis すら落ちたときの最後の砦です。Honeypot 内の deque（最大10,000件）に一時保持し、Redis 復旧後に flush します。

これにより「イベントが完全に消失するシナリオ」は「Honeypot 自体のプロセスが kill される + Redis も同時に落ちている」という極端なケースに限定されます。

### なぜ asyncio ベースにしたか

Honeypot は大量の同時接続を捌く必要があります。SSH Brute Force 攻撃では1分間に数百の接続が来ることがあります。

- スレッドベース: 1接続 = 1スレッドではメモリ・スケジュール面で非効率
- asyncio: 数千の同時接続を1プロセスで軽量に処理可能
- asyncssh / aiohttp がネイティブに async 対応している

### なぜ PostgreSQL を選んだか

攻撃ログは時系列データですが、Phase 2 以降で:

- IP 別集計（GROUP BY + 集計関数）
- 複雑なフィルタ（期間 + プロトコル + IP の組み合わせ）
- 全文検索（raw_data 内の JSON パス検索）

が必要になります。これらは RDBMS が得意な領域です。TimescaleDB への拡張も容易です。

### なぜパスワードを平文で保存するか

Honeypot は攻撃者が使うパスワードを記録します。ここには2つの選択肢がありました:

- **ハッシュ保存**: DB 漏洩時の二次被害を防ぐ
- **平文保存**: 辞書攻撃の傾向分析、パスワードランキング、攻撃辞書の特定が可能

本プロジェクトでは**分析価値を優先して平文保存**を選択しました。根拠:

1. 先行事例（Cowrie 等の Honeypot 研究）は平文記録が標準
2. 「どんなパスワードが試されているか」の可視化がポートフォリオとして価値が高い
3. DB 自体が外部非公開・認証必須なのでアクセス制御で保護

リスク認識: DB が漏洩した場合、攻撃者のパスワードリストとして悪用される可能性があります。本番運用では DB のアクセス制御とバックアップの暗号化で対処します。

## ネットワーク構成

```
┌─────────────────────────────────────────────┐
│ honeypot_net (bridge)                       │
│                                             │
│  ┌───────────────┐                          │
│  │   Honeypot    │ ← 外部公開 (0.0.0.0)     │
│  └───────┬───────┘                          │
│          │                                  │
├──────────┼──────────────────────────────────┤
│ internal_net (bridge)                       │
│          │                                  │
│  ┌───────▼───────┐  ┌──────┐  ┌──────────┐ │
│  │    Redis      │  │  DB  │  │  API     │ │
│  └───────────────┘  └──────┘  └──────────┘ │
│                                  │          │
│                       ┌──────────▼────────┐ │
│                       │    Dashboard      │ │
│                       └───────────────────┘ │
└─────────────────────────────────────────────┘
```

- Honeypot は `honeypot_net` と `internal_net` の両方に接続（外部アクセスを受けつつ Redis に投入）
- DB / Redis はポート公開が `127.0.0.1` のみ（外部から直接接続不可）
- API / Dashboard も `127.0.0.1` のみ（本番では VPN 経由でアクセス）

## データフロー詳細

### 1. SSH 攻撃の記録

```
攻撃者 → SSH(:2222) → SSHHoneypotServer.validate_password()
  → パスワードを平文のまま記録
  → AttackEvent 生成
  → EventQueue.publish() → Redis Stream (XADD)
  → Event Worker (XREADGROUP)
  → AttackEventModel → PostgreSQL (INSERT)
```

### 2. HTTP 攻撃の記録

```
攻撃者 → HTTP(:8080) → HTTPHoneypot._handle_request()
  → リクエスト情報を収集（ヘッダー、ボディ先頭1024B）
  → レスポンス戦略を決定（パス別）
  → AttackEvent 生成
  → EventQueue.publish() → Redis Stream
  → Worker → PostgreSQL
```

### 3. Dashboard での表示

```
ブラウザ → Nginx(:3000) → /api/* → proxy_pass → FastAPI(:8000)
  → Basic Auth 検証
  → AttackEventRepository → PostgreSQL (SELECT)
  → JSON レスポンス → React 描画
```

## 収集データ一覧

### SSH イベント

| フィールド | 型 | 用途 |
|-----------|-----|------|
| username | string | 辞書攻撃パターン分析 |
| password | string (平文) | パスワード傾向分析、辞書ファイル特定 |
| client_version | string | ボットネット・ツール特定 |
| connection_duration | float | 自動化 vs 手動の判別 |

### HTTP イベント

| フィールド | 型 | 用途 |
|-----------|-----|------|
| method + path | string | スキャン対象の特定 |
| user_agent | string | スキャナー特定 (Nmap, Nikto 等) |
| headers | dict | 攻撃ツールのフィンガープリント |
| body_preview | string (1024B) | Command Injection 検出 |

## 今後の拡張ポイント

| Phase | 拡張内容 | アーキテクチャへの影響 |
|-------|---------|---------------------|
| Phase 2 | 攻撃分類エンジン | Worker 内に Classification ステップを追加 |
| Phase 3 | MITRE ATT&CK mapping | 別モジュール追加（detection/mitre.py） |
| Phase 3 | GeoIP | Worker で記録時に国コード・ASN を付与 |
| Phase 4 | AI 分析 | 別サービスとして追加。API 経由でログを渡す |
| Phase 4 | SSH 疑似シェル | 認証を限定的に成功させ、コマンド入力を記録 |
