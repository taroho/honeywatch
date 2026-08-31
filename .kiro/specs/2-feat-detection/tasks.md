# Implementation Plan

## Overview

Phase 2（Detection）の実装計画。DB スキーマ拡張 → Detection Rule 基盤 → 分類エンジン → Worker 統合 → IP 分析・Risk Score → 分析 API → Dashboard 拡張の順で実装する。Phase 1 のパイプラインを壊さないよう、既存の Worker に分類ステップを追加する形で進める。

## Tasks

- [x] 1. DB スキーマ拡張: attack_events テーブルに attack_type / severity カラム（nullable, index 付き）を追加。Alembic マイグレーション作成・適用。AttackEventModel を更新
- [x] 2. Detection Rule 基盤: config/detection_rules.yaml を作成。detection/patterns.py に DetectionRuleLoader（YAML 読み込み・バリデーション、起動時検証）を実装
- [x] 3. 攻撃分類エンジン: detection/classifier.py に AttackClassifier（brute_force, port_scan, http_scan, credential_attack, command_injection, suspicious_request の判定）と SeverityEvaluator（HIGH/MEDIUM/LOW 判定）を実装
- [x] 4. IPContext 管理: 同一 IP の時間窓内試行回数を Redis カウンタ（honeywatch:ipctx:<ip>, TTL 付き）で管理するロジックを実装。Redis 取得失敗時は degraded 動作
- [x] 5. Worker への分類ステップ統合: tasks/workers.py で保存前に AttackClassifier を呼び、attack_type / severity を付与。分類例外時は suspicious_request にフォールバック
- [x] 6. バッチ再分類: detection/backfill.py を作成。未分類イベント（attack_type IS NULL）を時系列順に再分類する `python -m honeywatch.detection.backfill` を実装
- [x] 7. IP 分析・Risk Score: analysis/ip.py に IPAnalyzer（IP プロファイル集約）と RiskScorer（頻度・多様性・Severity から 0〜100 算出）を実装
- [x] 8. Repository 拡張: db/repositories/attack.py に攻撃タイプ別集計、Severity 別集計、Risk ランキング用のクエリメソッドを追加
- [x] 9. 分析 API: api/routes/analysis.py に GET /analysis/attack-types, /analysis/ips/{source_ip}, /analysis/risk-ranking, /analysis/severity-summary を実装。main.py にルーター登録
- [x] 10. Dashboard 拡張: 攻撃タイプ別グラフ、Severity 別表示、Risk ランキング、IP 詳細ページを追加。対応する型定義・hooks・API クライアントを実装
- [ ] 11. テスト: AttackClassifier / SeverityEvaluator / RiskScorer / DetectionRuleLoader のユニットテストは実装済み（32件 pass）。分析 API の結合テストは未実装（AWS 実データ後に追加予定）
- [x] 12. 動作確認・ドキュメント更新: バッチ再分類の実行確認、分類結果が Dashboard に反映されることを確認。docs/architecture.md に Detection レイヤーを追記

## Task Dependency Graph

```json
{
  "waves": [
    [1, 2],
    [3, 4],
    [5, 6, 7],
    [8],
    [9],
    [10],
    [11, 12]
  ]
}
```

## Notes

- Task 1（DB）と Task 2（Rule 基盤）は並列実行可能
- Task 3（分類エンジン）は Task 2 のルール定義に依存
- Task 5（Worker 統合）は Task 3, 4 完了後
- Task 6（バッチ再分類）は Task 3 完了後に実装可能
- Task 10（Dashboard）は Task 9（API）完了後
- Phase 1 のパイプラインを壊さないよう、各ステップで既存の動作確認を行う
