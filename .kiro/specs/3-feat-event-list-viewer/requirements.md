# Requirements Document

## Introduction

Dashboard に、収集済みの攻撃イベント（リクエスト）を一覧・絞り込み・ページ送りで閲覧し、任意のイベントの詳細（リクエスト内容 = `raw_data`）を確認できる画面を追加する。現状 Dashboard には直近イベントの簡易テーブル（`RecentEventsTable`、直近10件・詳細不可）しか無く、過去のイベントを網羅的に辿ったり、個別リクエストの中身を確認する手段が無い。本機能でこれを解消する。

本機能は既存のイベント一覧 API（`GET /api/v1/events`、ページネーション・フィルタ対応済み）を利用し、バックエンドの新規エンドポイントは追加しない。フロントエンドはルーティングライブラリを追加せず、`App.tsx` 内のビュー切替でダッシュボードと一覧画面を行き来する。

## Glossary

| 用語 | 説明 |
|------|------|
| Event List View | 攻撃イベントを一覧表示する専用画面 |
| Event Detail Modal | 1件の攻撃イベントの詳細（リクエスト内容）をモーダルで表示する UI |
| Raw Data | イベントのプロトコル固有データ（`raw_data`、リクエスト内容を含む JSON） |
| Filter | protocol / source_ip / 期間による絞り込み条件 |
| Pagination | ページ番号・件数指定によるページ送り |
| View | `App.tsx` が出し分けるダッシュボード / 一覧の表示単位 |

## Requirements

### Requirement 1: イベント一覧表示

**User Story:** セキュリティ担当者として、収集済みの攻撃イベントを一覧で確認したい。そうすれば、観測された攻撃の全体像を把握できる。

#### Acceptance Criteria

1. WHEN 認証済みユーザーが一覧画面を開く THEN THE SYSTEM SHALL 攻撃イベントを新しい順（timestamp 降順）でテーブル表示する
2. WHERE 各行を表示する THE SYSTEM SHALL 発生時刻・送信元 IP・送信元ポート・宛先ポート・プロトコル・イベントタイプを表示する
3. WHEN 表示対象のイベントが 0 件である THEN THE SYSTEM SHALL 「イベントがありません」旨の空状態を表示する

### Requirement 2: ページネーション

**User Story:** セキュリティ担当者として、大量のイベントをページ送りで辿りたい。そうすれば、過去のイベントも含めてすべて閲覧できる。

#### Acceptance Criteria

1. WHEN 一覧画面が表示される THEN THE SYSTEM SHALL ページ単位（1ページあたり最大 100 件、既定 50 件）でイベントを取得・表示する
2. WHEN ユーザーが次ページ・前ページを操作する THEN THE SYSTEM SHALL 対応するページのイベントを取得して表示する
3. THE SYSTEM SHALL 現在のページ番号・総ページ数・総件数を表示する
4. WHERE 総イベント数が 1 ページに収まらない THE SYSTEM SHALL ページ送りによってすべてのイベントに到達できる

### Requirement 3: フィルタ

**User Story:** セキュリティ担当者として、プロトコル・送信元 IP・期間でイベントを絞り込みたい。そうすれば、調査対象のイベントだけを素早く抽出できる。

#### Acceptance Criteria

1. WHEN ユーザーがプロトコル（ssh / http）を指定する THEN THE SYSTEM SHALL 該当プロトコルのイベントのみを表示する
2. WHEN ユーザーが送信元 IP を指定する THEN THE SYSTEM SHALL 該当 IP のイベントのみを表示する
3. WHEN ユーザーが期間（開始・終了日時）を指定する THEN THE SYSTEM SHALL 該当期間内のイベントのみを表示する
4. WHEN フィルタ条件が変更される THEN THE SYSTEM SHALL ページを 1 ページ目にリセットして再取得する
5. WHEN ユーザーがフィルタをクリアする THEN THE SYSTEM SHALL すべてのフィルタを解除して全イベント（新しい順）を表示する

### Requirement 4: 詳細表示（リクエスト内容）

**User Story:** セキュリティ担当者として、個別イベントのリクエスト内容を確認したい。そうすれば、攻撃の具体的な中身を分析できる。

#### Acceptance Criteria

1. WHEN ユーザーが一覧の行または「詳細」操作をクリックする THEN THE SYSTEM SHALL 該当イベントの詳細をモーダルで表示する
2. WHERE 詳細モーダルを表示する THE SYSTEM SHALL イベントの基本情報（時刻・IP・ポート・プロトコル・イベントタイプ）と、リクエスト内容（`raw_data`）を整形して表示する
3. WHEN ユーザーがモーダルを閉じる操作を行う THEN THE SYSTEM SHALL モーダルを閉じ、一覧の表示状態（ページ・フィルタ）を維持する

### Requirement 5: 画面遷移（ビュー切替）

**User Story:** ユーザーとして、ダッシュボードと一覧画面を切り替えたい。そうすれば、追加のライブラリ導入なしで両画面を行き来できる。

#### Acceptance Criteria

1. WHEN 認証済みユーザーがナビゲーション操作を行う THEN THE SYSTEM SHALL ダッシュボードと一覧画面をルーティングライブラリなしで切り替える
2. WHERE 未認証の状態である THE SYSTEM SHALL 一覧画面を表示せず、ログイン画面を表示する

### Requirement 6: 通信・エラー処理

**User Story:** ユーザーとして、データ取得に失敗しても画面が壊れないでほしい。そうすれば、安心して操作を続けられる。

#### Acceptance Criteria

1. WHEN 一覧または詳細のデータ取得に失敗する THEN THE SYSTEM SHALL エラー状態をユーザーに表示する（画面がクラッシュしない）
2. WHEN API が 401（認証失敗）を返す THEN THE SYSTEM SHALL 既存の認証処理に従いログイン画面へ戻す

### Requirement 7: 非機能要件（依存・一貫性・非変更・性能）

**User Story:** 開発者として、既存スタックと整合した形で本機能を実装したい。そうすれば、保守性と後方互換を保てる。

#### Acceptance Criteria

1. WHEN 本機能を実装する THEN THE SYSTEM SHALL 新しい npm 依存関係を追加せず、既存のスタック（React / TypeScript / TailwindCSS / fetch ベース API クライアント）のみで実現する
2. WHEN UI を実装する THEN THE SYSTEM SHALL 既存 Dashboard のデザイントークン（`hw-*` カラー、カード・ボーダースタイル）と命名規則に従う
3. WHEN 一覧・詳細データを取得する THEN THE SYSTEM SHALL 既存の `GET /api/v1/events` のみを利用し、バックエンドのエンドポイントを追加・変更しない（詳細は一覧取得時の `raw_data` を利用する）
4. WHEN 大量のイベントが存在する THEN THE SYSTEM SHALL 全件を一括取得せず、ページネーションで段階的に取得する
