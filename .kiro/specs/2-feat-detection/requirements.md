# Requirements Document

## Introduction

Phase 2 では、Phase 1 で収集した攻撃イベントを分析する機能を実装する。攻撃タイプの自動分類、送信元 IP 単位の分析とリスクスコア算出、攻撃深刻度（Severity）判定、タイムライン分析の強化を行う。判定基準は設定ファイルで柔軟に変更できるようにする。

## Glossary

| 用語 | 説明 |
|------|------|
| Attack Classification | 攻撃イベントを Brute Force, Port Scan 等のタイプに分類すること |
| Severity | 攻撃の深刻度（HIGH / MEDIUM / LOW） |
| Risk Score | 送信元 IP ごとの危険度を数値化したスコア（0〜100） |
| Detection Rule | 攻撃分類・Severity 判定の基準を定義したルール（YAML で管理） |
| IP Profile | 送信元 IP 単位で集約した攻撃履歴・統計情報 |

## Requirements

### Requirement 1: 攻撃タイプ分類

**User Story:** アナリストとして、攻撃イベントを種類ごとに自動分類したい。そうすれば、攻撃の傾向を把握しやすくなる。

#### Acceptance Criteria

1. WHEN 新しい攻撃イベントが保存される THEN THE SYSTEM SHALL イベントを以下のいずれかの攻撃タイプに分類する: Brute Force, Port Scan, HTTP Scan, Credential Attack, Command Injection, Suspicious Request
2. WHEN 攻撃タイプを判定する THEN THE SYSTEM SHALL 設定ファイル（Detection Rule）に定義された基準に従って分類する

### Requirement 2: Severity 判定

**User Story:** アナリストとして、各攻撃の深刻度を把握したい。そうすれば、優先的に対応すべき攻撃を判別できる。

#### Acceptance Criteria

1. WHEN 攻撃イベントが分類される THEN THE SYSTEM SHALL 攻撃タイプと閾値に基づいて Severity（HIGH / MEDIUM / LOW）を付与する
2. WHEN Detection Rule の閾値が変更される THEN THE SYSTEM SHALL 再起動のみで新しい基準を反映する（コード変更不要）

### Requirement 3: IP 分析・Risk Score

**User Story:** アナリストとして、送信元 IP ごとの危険度を把握したい。そうすれば、脅威度の高い IP を特定できる。

#### Acceptance Criteria

1. WHEN 送信元 IP の分析が要求される THEN THE SYSTEM SHALL 該当 IP の攻撃履歴（初回・最終観測時刻、総イベント数、攻撃タイプ一覧）を返す
2. WHEN IP の Risk Score を算出する THEN THE SYSTEM SHALL 攻撃頻度、攻撃タイプの多様性、Severity を考慮して 0〜100 のスコアを算出する

### Requirement 4: Timeline 分析の強化

**User Story:** アナリストとして、時間帯別の攻撃傾向を種類別・深刻度別に見たい。そうすれば、攻撃の時間的な特徴を分析できる。

#### Acceptance Criteria

1. WHEN タイムラインが要求される THEN THE SYSTEM SHALL 時間帯別のイベント数を攻撃タイプ別・Severity 別に集計して返す

### Requirement 5: 分類結果の永続化

**User Story:** アナリストとして、分類結果を保存し既存データにも遡及したい。そうすれば、過去データも分類済みとして分析できる。

#### Acceptance Criteria

1. WHEN 攻撃イベントが分類される THEN THE SYSTEM SHALL 分類結果（attack_type, severity）をイベントレコードに保存する
2. WHEN 既存の未分類イベントが存在する THEN THE SYSTEM SHALL バッチ処理で遡って分類できる

### Requirement 6: 分析 API の提供

**User Story:** Dashboard 開発者として、分析データを API から取得したい。そうすれば、分析結果を可視化できる。

#### Acceptance Criteria

1. WHEN Dashboard が分析データを要求する THEN THE SYSTEM SHALL 攻撃タイプ別集計を API エンドポイント経由で提供する
2. WHEN Dashboard が分析データを要求する THEN THE SYSTEM SHALL IP 別 Risk Score ランキングを API エンドポイント経由で提供する
3. WHEN Dashboard が分析データを要求する THEN THE SYSTEM SHALL IP 詳細プロファイルを API エンドポイント経由で提供する
4. WHEN Dashboard が分析データを要求する THEN THE SYSTEM SHALL Severity 別統計を API エンドポイント経由で提供する

### Requirement 7: パフォーマンス

**User Story:** 運用者として、分析処理が観測基盤の性能を損なわないようにしたい。そうすれば、収集と分析を両立できる。

#### Acceptance Criteria

1. WHEN 攻撃分類を実行する THEN THE SYSTEM SHALL イベント保存のレイテンシに大きな影響を与えない（分類処理は 100ms 以内）
2. WHEN IP 分析クエリを実行する THEN THE SYSTEM SHALL 1 秒以内にレスポンスを返す

### Requirement 8: 拡張性

**User Story:** 開発者として、新しい攻撃タイプを容易に追加したい。そうすれば、コード変更を最小限に運用できる。

#### Acceptance Criteria

1. WHEN 新しい攻撃タイプを追加する THEN THE SYSTEM SHALL Detection Rule への追記のみで対応でき、既存コードの変更を最小限にする

### Requirement 9: 後方互換性

**User Story:** 運用者として、Phase 2 追加後も既存データを保持したい。そうすれば、収集済みイベントを失わずに機能拡張できる。

#### Acceptance Criteria

1. WHEN Phase 2 の機能を追加する THEN THE SYSTEM SHALL Phase 1 で収集済みのイベントデータを破壊しない（マイグレーションで拡張する）
