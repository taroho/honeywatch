# Design

## Overview

Phase 2 では、Phase 1 のイベント収集パイプラインに「分類・分析」レイヤーを追加する。Event Worker がイベントを DB に保存する際、Detection エンジンで攻撃タイプと Severity を判定し、結果をイベントレコードに付与する。さらに IP 単位の分析と Risk Score 算出を行い、分析用 API を提供する。

### 設計方針

- Phase 1 のパイプラインを壊さず、Worker に分類ステップを追加する形で拡張する
- 判定基準は YAML の Detection Rule で管理し、コード変更なしで調整可能にする
- 攻撃タイプ・Severity はイベントレコードに保存し、集計クエリを高速化する
- IP 分析は既存の attack_events テーブルへの集計クエリで実現し、必要に応じてキャッシュする

## Architecture

Phase 1 のフローに Detection ステップを追加する。

```
                Honeypots
                   │ XADD
                   ▼
              Redis Stream
                   │ XREADGROUP
                   ▼
          ┌─────────────────┐
          │  Event Worker   │
          │  ┌───────────┐  │
          │  │ Detection │  │ ← NEW: 攻撃分類 + Severity 判定
          │  └───────────┘  │
          └────────┬────────┘
                   │ INSERT (attack_type, severity 付き)
                   ▼
              PostgreSQL
                   │
                   ▼
          ┌─────────────────┐
          │  FastAPI API    │
          │  + 分析 API     │ ← NEW: IP 分析, Risk Score
          └────────┬────────┘
                   │
                   ▼
              Dashboard
```

### 変更点

- **Event Worker**: 保存前に `AttackClassifier` を呼び、`attack_type` と `severity` を判定
- **DB スキーマ**: `attack_events` テーブルに `attack_type`, `severity` カラムを追加
- **API**: 分析エンドポイント群を追加
- **設定**: `config/detection_rules.yaml` を追加

## Components and Interfaces

| コンポーネント | 責務 | 配置 |
|--------------|------|------|
| AttackClassifier | イベントを攻撃タイプに分類 | detection/classifier.py |
| SeverityEvaluator | 攻撃タイプ・閾値から Severity を判定 | detection/classifier.py |
| DetectionRuleLoader | YAML ルールの読み込み・管理 | detection/patterns.py |
| RiskScorer | IP ごとの Risk Score を算出 | analysis/ip.py |
| IPAnalyzer | IP プロファイルを集約 | analysis/ip.py |
| AttackEventRepository（拡張） | 分類結果込みのクエリ | db/repositories/attack.py |

### AttackClassifier インターフェース

```python
class AttackClassifier:
    def __init__(self, rules: DetectionRules): ...

    async def classify(
        self, event: AttackEvent, context: IPContext
    ) -> ClassificationResult:
        """イベントを分類し、attack_type と severity を返す"""
        ...
```

- `IPContext`: 直近の同一 IP からのイベント履歴（Brute Force の試行回数カウント等に使用）
- `ClassificationResult`: `attack_type`, `severity` を含む

## Data Models

### DB スキーマ拡張（attack_events テーブル）

```python
class AttackEventModel(Base):
    # --- Phase 1 の既存カラム ---
    # id, timestamp, source_ip, source_port,
    # destination_port, protocol, event_type, raw_data, created_at

    # --- Phase 2 で追加 ---
    attack_type: Mapped[str | None] = mapped_column(String(30), index=True)
    severity: Mapped[str | None] = mapped_column(String(10), index=True)
```

- 既存レコードとの互換性のため nullable とする（未分類は NULL）
- `attack_type`, `severity` にインデックスを付与（集計クエリの高速化）

### 攻撃タイプ

| attack_type | 説明 | 主な判定材料 |
|-------------|------|-------------|
| brute_force | SSH 認証の反復試行 | 同一 IP からの試行回数・時間窓 |
| port_scan | 複数ポートへの接続 | 同一 IP の宛先ポート種類数 |
| http_scan | Web パスのスキャン | /admin, /phpmyadmin 等へのアクセス |
| credential_attack | 既知の弱いユーザー名/パスワード | ユーザー名・パスワードの辞書一致 |
| command_injection | コマンドインジェクション試行 | リクエストボディ・パスのパターン |
| suspicious_request | 上記に該当しない不審なアクセス | デフォルト分類 |

### Severity

| severity | 意味 |
|----------|------|
| HIGH | 明確な攻撃・自動化された大量試行 |
| MEDIUM | 疑わしい活動 |
| LOW | 単発・軽度のスキャン |

### Detection Rule（YAML）

```yaml
# config/detection_rules.yaml
attack_types:
  brute_force:
    protocol: ssh
    min_attempts: 5
    time_window: 600
  port_scan:
    min_distinct_ports: 5
    time_window: 300
  http_scan:
    paths: ["/admin", "/wp-admin", "/phpmyadmin", "/.env"]
  command_injection:
    patterns: [";", "|", "$(", "&&", "../"]

severity_rules:
  HIGH:
    - attack_type: brute_force
      min_attempts: 100
    - attack_type: command_injection
  MEDIUM:
    - attack_type: brute_force
      min_attempts: 20
    - attack_type: port_scan
  LOW:
    - attack_type: http_scan
    - attack_type: suspicious_request
```

### Risk Score 算出ロジック

```
risk_score = min(100, 攻撃頻度スコア + 多様性スコア + Severity スコア)

- 攻撃頻度スコア: イベント数に応じて 0〜40
- 多様性スコア: 異なる攻撃タイプ数 × 10（最大 30）
- Severity スコア: HIGH=30, MEDIUM=15, LOW=5（最大値を採用）
```

## API Endpoints

### GET /api/v1/analysis/attack-types

攻撃タイプ別の集計を返す。

**Query Parameters:** `period`（1h/6h/24h/7d）

### GET /api/v1/analysis/ips/{source_ip}

指定 IP の詳細プロファイルを返す。

**Response:**
```json
{
  "source_ip": "185.x.x.x",
  "first_seen": "...",
  "last_seen": "...",
  "total_events": 342,
  "attack_types": ["brute_force", "http_scan"],
  "risk_score": 87,
  "risk_level": "HIGH"
}
```

### GET /api/v1/analysis/risk-ranking

Risk Score の高い IP ランキングを返す。

**Query Parameters:** `limit`, `period`

### GET /api/v1/analysis/severity-summary

Severity 別のイベント件数を返す。

## Detection Design

### 分類フロー

1. Worker がイベントを受信
2. `IPContext` を構築（同一 IP の直近イベントを Redis から取得、または DB クエリ）
3. `AttackClassifier.classify()` で attack_type を判定
4. `SeverityEvaluator` で severity を判定
5. attack_type + severity を付与して DB に保存

### IPContext の管理

- Brute Force / Port Scan は「時間窓内の試行回数」を見る必要がある
- Redis に IP ごとのカウンタを保持（`honeywatch:ipctx:<ip>`, TTL 付き）
- Worker は分類時にこのカウンタを参照・更新する

### バッチ再分類

- Phase 1 で収集済みの未分類イベント（attack_type IS NULL）を対象
- `python -m honeywatch.detection.backfill` で実行
- 時系列順に IPContext を再構築しながら分類

## Error Handling

| 障害シナリオ | 対処 |
|------------|------|
| Detection Rule の YAML パースエラー | 起動時に検証し、不正なら起動を中断してログ出力 |
| 分類処理中の例外 | イベントは suspicious_request として保存し、分類は継続（イベント消失を防ぐ） |
| IPContext（Redis）取得失敗 | 時間窓カウントなしで分類（degraded だが動作継続） |

## Testing Strategy

| レイヤー | テスト手法 | ツール |
|---------|-----------|--------|
| AttackClassifier | ユニットテスト（各攻撃タイプの判定） | pytest |
| SeverityEvaluator | ユニットテスト（閾値境界値） | pytest |
| RiskScorer | ユニットテスト（スコア算出ロジック） | pytest |
| DetectionRuleLoader | ユニットテスト（YAML パース・バリデーション） | pytest |
| 分析 API | 結合テスト | pytest + httpx |
| バッチ再分類 | 結合テスト | pytest + testcontainers |

## Correctness Properties

### Property 1: 分類失敗時のイベント保持

分類処理が失敗してもイベントは必ず保存される（suspicious_request にフォールバック）。

**Validates: Requirements 5.1**

### Property 2: ルール変更の反映

Detection Rule 変更後、再起動のみで新基準が反映される（コード変更不要）。

**Validates: Requirements 2.2, 8.1**

### Property 3: 既存データの非破壊

Phase 1 の既存イベントデータは破壊されない（追加カラムは nullable）。

**Validates: Requirements 9.1**

### Property 4: Risk Score の範囲

Risk Score は必ず 0〜100 の範囲に収まる。

**Validates: Requirements 3.2**

### Property 5: 分類の決定性

同一イベントを再分類しても結果は決定的（同じ入力 → 同じ分類）。

**Validates: Requirements 1.2, 5.2**
