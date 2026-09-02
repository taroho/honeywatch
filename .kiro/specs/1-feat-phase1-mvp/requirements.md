# Requirements Document

## Introduction

Phase 1 MVP として、HoneyWatch の基盤を構築する。SSH / HTTP の Honeypot でインターネット上の攻撃トラフィックを観測し、イベントとして収集・保存し、基本的な Dashboard で可視化する。

## Glossary

| 用語 | 説明 |
|------|------|
| Honeypot | 攻撃者を引き寄せるために意図的に公開する偽サービス |
| Attack Event | Honeypot が観測した1回の攻撃的アクセスを表すイベントレコード |
| Event Queue | Honeypot からワーカーへイベントを受け渡す Redis Stream ベースのキュー |
| Event Worker | キューからイベントを取得し DB に永続化するバックグラウンドプロセス |
| Dashboard | 攻撃状況を可視化する Web UI |

## Requirements

### Requirement 1: SSH Honeypot

**User Story:** セキュリティ運用者として、SSH への攻撃を観測したい。そうすれば、SSH に対する不正アクセス試行を記録・分析できる。

#### Acceptance Criteria

1. WHEN 外部から SSH 接続が試みられる THEN THE SYSTEM SHALL 接続情報（送信元 IP、ポート、ユーザー名、パスワードハッシュ、タイムスタンプ、接続時間）をイベントとして記録する
2. WHEN SSH 認証が試みられる THEN THE SYSTEM SHALL 常に認証を失敗させる（ログインを許可しない）

### Requirement 2: HTTP Honeypot

**User Story:** セキュリティ運用者として、HTTP への攻撃を観測したい。そうすれば、Web に対するスキャンや攻撃試行を記録・分析できる。

#### Acceptance Criteria

1. WHEN 外部から HTTP リクエストが送信される THEN THE SYSTEM SHALL リクエスト情報（送信元 IP、メソッド、パス、ヘッダー、User-Agent、タイムスタンプ）をイベントとして記録する
2. WHEN HTTP リクエストを受信する THEN THE SYSTEM SHALL 一般的な Web サーバーを模したレスポンスを返す

### Requirement 3: Event Collection

**User Story:** システムとして、観測したイベントを確実にキュー経由で収集したい。そうすれば、Honeypot と永続化を疎結合に保てる。

#### Acceptance Criteria

1. WHEN Honeypot がイベントを検知する THEN THE SYSTEM SHALL イベントを共通フォーマットに正規化してキューに投入する
2. WHEN キューにイベントが存在する THEN THE SYSTEM SHALL キューからイベントを取得してデータベースに永続化する

### Requirement 4: Event Storage

**User Story:** アナリストとして、観測イベントを永続化したい。そうすれば、後から検索・分析できる。

#### Acceptance Criteria

1. WHEN 正規化されたイベントがワーカーに処理される THEN THE SYSTEM SHALL PostgreSQL に攻撃イベントレコードとして保存する
2. WHEN イベントが保存される THEN THE SYSTEM SHALL 最低限以下のフィールドを含む: timestamp, source_ip, destination_port, protocol, event_type, raw_data

### Requirement 5: REST API

**User Story:** Dashboard 開発者として、可視化に必要なデータを API から取得したい。そうすれば、フロントエンドを疎結合に構築できる。

#### Acceptance Criteria

1. WHEN Dashboard がデータを要求する THEN THE SYSTEM SHALL 攻撃イベント一覧（ページネーション付き）を API エンドポイント経由で提供する
2. WHEN Dashboard がデータを要求する THEN THE SYSTEM SHALL 統計サマリー（本日の攻撃数、ユニーク IP 数、プロトコル別件数）を API エンドポイント経由で提供する
3. WHEN Dashboard がデータを要求する THEN THE SYSTEM SHALL 時間帯別イベント数（タイムライン用）を API エンドポイント経由で提供する
4. WHEN Dashboard がデータを要求する THEN THE SYSTEM SHALL 送信元 IP ランキングを API エンドポイント経由で提供する

### Requirement 6: Basic Dashboard

**User Story:** ユーザーとして、攻撃状況を Dashboard で把握したい。そうすれば、観測状況を一目で確認できる。

#### Acceptance Criteria

1. WHEN ユーザーが Dashboard にアクセスする THEN THE SYSTEM SHALL 攻撃数サマリーカード（本日の攻撃数、ユニーク IP 数、SSH 試行数、HTTP 攻撃数）を表示する
2. WHEN ユーザーが Dashboard にアクセスする THEN THE SYSTEM SHALL 攻撃タイムライン（時間帯別の折れ線グラフ）を表示する
3. WHEN ユーザーが Dashboard にアクセスする THEN THE SYSTEM SHALL Top 送信元 IP リストを表示する
4. WHEN ユーザーが Dashboard にアクセスする THEN THE SYSTEM SHALL 最新イベントテーブルを表示する

### Requirement 7: セキュリティ

**User Story:** 運用者として、Honeypot と管理系を安全に運用したい。そうすれば、攻撃観測基盤自体のリスクを抑えられる。

#### Acceptance Criteria

1. WHEN Honeypot プロセスが実行される THEN THE SYSTEM SHALL 最小権限で動作し、管理用 API と異なるネットワークインターフェースで待ち受ける
2. WHEN パスワードが記録される THEN THE SYSTEM SHALL 平文で保存する（攻撃パターン分析・辞書攻撃傾向の可視化に使用。DB アクセス制御で保護）
3. WHEN Dashboard API にアクセスされる THEN THE SYSTEM SHALL 認証で保護する（Phase 1 では Basic Auth）

### Requirement 8: パフォーマンス

**User Story:** 運用者として、負荷時でも安定して観測・応答したい。そうすれば、大量の攻撃時にも取りこぼしを防げる。

#### Acceptance Criteria

1. WHEN 同時に多数の SSH 接続がある THEN THE SYSTEM SHALL 100 以上の同時接続を処理できる
2. WHEN イベントが発生する THEN THE SYSTEM SHALL 500ms 以内にデータベースに保存する
3. WHEN Dashboard API にリクエストがある THEN THE SYSTEM SHALL 1 秒以内にレスポンスを返す

### Requirement 9: 可用性

**User Story:** 運用者として、障害時にもイベントを失いたくない。そうすれば、観測データの欠損を防げる。

#### Acceptance Criteria

1. WHEN Honeypot プロセスがクラッシュする THEN THE SYSTEM SHALL 自動再起動する
2. WHEN DB 接続エラーが発生する THEN THE SYSTEM SHALL イベントをキューに保持し、復旧後に再処理する

### Requirement 10: 運用性

**User Story:** 運用者として、デプロイと設定変更を容易にしたい。そうすれば、環境構築や切り替えを素早く行える。

#### Acceptance Criteria

1. WHEN システムをデプロイする THEN THE SYSTEM SHALL Docker Compose で全コンポーネントを一括起動できる
2. WHEN 環境を切り替える THEN THE SYSTEM SHALL 環境変数で設定を変更できる
3. WHEN ログを出力する THEN THE SYSTEM SHALL 構造化ログ（JSON 形式）で出力する
