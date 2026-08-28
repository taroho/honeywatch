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

### FR-1: SSH Honeypot

WHEN 外部から SSH 接続が試みられる
THE SYSTEM SHALL 接続情報（送信元 IP、ポート、ユーザー名、パスワードハッシュ、タイムスタンプ、接続時間）をイベントとして記録する

WHEN SSH 認証が試みられる
THE SYSTEM SHALL 常に認証を失敗させる（ログインを許可しない）

### FR-2: HTTP Honeypot

WHEN 外部から HTTP リクエストが送信される
THE SYSTEM SHALL リクエスト情報（送信元 IP、メソッド、パス、ヘッダー、User-Agent、タイムスタンプ）をイベントとして記録する

WHEN HTTP リクエストを受信する
THE SYSTEM SHALL 一般的な Web サーバーを模したレスポンスを返す

### FR-3: Event Collection

WHEN Honeypot がイベントを検知する
THE SYSTEM SHALL イベントを共通フォーマットに正規化してキューに投入する

WHEN キューにイベントが存在する
THE SYSTEM SHALL キューからイベントを取得してデータベースに永続化する

### FR-4: Event Storage

WHEN 正規化されたイベントがワーカーに処理される
THE SYSTEM SHALL PostgreSQL に攻撃イベントレコードとして保存する

WHEN イベントが保存される
THE SYSTEM SHALL 最低限以下のフィールドを含む: timestamp, source_ip, destination_port, protocol, event_type, raw_data

### FR-5: REST API

WHEN Dashboard がデータを要求する
THE SYSTEM SHALL 以下のデータを API エンドポイント経由で提供する: 攻撃イベント一覧（ページネーション付き）、統計サマリー（本日の攻撃数、ユニーク IP 数、プロトコル別件数）、時間帯別イベント数（タイムライン用）、送信元 IP ランキング

### FR-6: Basic Dashboard

WHEN ユーザーが Dashboard にアクセスする
THE SYSTEM SHALL 以下の情報を表示する: 攻撃数サマリーカード（本日の攻撃数、ユニーク IP 数、SSH 試行数、HTTP 攻撃数）、攻撃タイムライン（時間帯別の折れ線グラフ）、Top 送信元 IP リスト、最新イベントテーブル

### NFR-1: セキュリティ

WHEN Honeypot プロセスが実行される
THE SYSTEM SHALL 最小権限で動作し、管理用 API と異なるネットワークインターフェースで待ち受ける

WHEN パスワードが記録される
THE SYSTEM SHALL 平文で保存する（攻撃パターン分析・辞書攻撃傾向の可視化に使用。DB アクセス制御で保護）

WHEN Dashboard API にアクセスされる
THE SYSTEM SHALL 認証で保護する（Phase 1 では Basic Auth）

### NFR-2: パフォーマンス

WHEN 同時に多数の SSH 接続がある
THE SYSTEM SHALL 100 以上の同時接続を処理できる

WHEN イベントが発生する
THE SYSTEM SHALL 500ms 以内にデータベースに保存する

WHEN Dashboard API にリクエストがある
THE SYSTEM SHALL 1 秒以内にレスポンスを返す

### NFR-3: 可用性

WHEN Honeypot プロセスがクラッシュする
THE SYSTEM SHALL 自動再起動する

WHEN DB 接続エラーが発生する
THE SYSTEM SHALL イベントをキューに保持し、復旧後に再処理する

### NFR-4: 運用性

WHEN システムをデプロイする
THE SYSTEM SHALL Docker Compose で全コンポーネントを一括起動できる

WHEN 環境を切り替える
THE SYSTEM SHALL 環境変数で設定を変更できる

WHEN ログを出力する
THE SYSTEM SHALL 構造化ログ（JSON 形式）で出力する
