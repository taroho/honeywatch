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

### FR-1: 攻撃タイプ分類

WHEN 新しい攻撃イベントが保存される
THE SYSTEM SHALL イベントを以下のいずれかの攻撃タイプに分類する: Brute Force, Port Scan, HTTP Scan, Credential Attack, Command Injection, Suspicious Request

WHEN 攻撃タイプを判定する
THE SYSTEM SHALL 設定ファイル（Detection Rule）に定義された基準に従って分類する

### FR-2: Severity 判定

WHEN 攻撃イベントが分類される
THE SYSTEM SHALL 攻撃タイプと閾値に基づいて Severity（HIGH / MEDIUM / LOW）を付与する

WHEN Detection Rule の閾値が変更される
THE SYSTEM SHALL 再起動のみで新しい基準を反映する（コード変更不要）

### FR-3: IP 分析・Risk Score

WHEN 送信元 IP の分析が要求される
THE SYSTEM SHALL 該当 IP の攻撃履歴（初回・最終観測時刻、総イベント数、攻撃タイプ一覧）を返す

WHEN IP の Risk Score を算出する
THE SYSTEM SHALL 攻撃頻度、攻撃タイプの多様性、Severity を考慮して 0〜100 のスコアを算出する

### FR-4: Timeline 分析の強化

WHEN タイムラインが要求される
THE SYSTEM SHALL 時間帯別のイベント数を攻撃タイプ別・Severity 別に集計して返す

### FR-5: 分類結果の永続化

WHEN 攻撃イベントが分類される
THE SYSTEM SHALL 分類結果（attack_type, severity）をイベントレコードに保存する

WHEN 既存の未分類イベントが存在する
THE SYSTEM SHALL バッチ処理で遡って分類できる

### FR-6: 分析 API の提供

WHEN Dashboard が分析データを要求する
THE SYSTEM SHALL 以下を API エンドポイント経由で提供する: 攻撃タイプ別集計、IP 別 Risk Score ランキング、IP 詳細プロファイル、Severity 別統計

## Non-Functional Requirements

### NFR-1: パフォーマンス

WHEN 攻撃分類を実行する
THE SYSTEM SHALL イベント保存のレイテンシに大きな影響を与えない（分類処理は 100ms 以内）

WHEN IP 分析クエリを実行する
THE SYSTEM SHALL 1 秒以内にレスポンスを返す

### NFR-2: 拡張性

WHEN 新しい攻撃タイプを追加する
THE SYSTEM SHALL Detection Rule への追記のみで対応でき、既存コードの変更を最小限にする

### NFR-3: 後方互換性

WHEN Phase 2 の機能を追加する
THE SYSTEM SHALL Phase 1 で収集済みのイベントデータを破壊しない（マイグレーションで拡張する）
