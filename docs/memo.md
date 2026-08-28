# 開発メモ

Phase 2 以降で実装する際に参考にする設計メモ。

## 攻撃 Severity（深刻度）判定の設計方針

### 要件

- 判定基準（閾値、パターン）をコード変更なしで柔軟に変えられるようにしたい
- 環境ごとに（開発 / 本番）別の設定を使い分けたい
- 再起動のみで反映される仕組み

### 方針: YAML ベースのルール定義

```yaml
# config/detection_rules.yaml
severity_rules:
  HIGH:
    - type: ssh_brute_force
      threshold: 100        # N回以上の試行で HIGH
      time_window: 600      # M秒以内
    - type: command_injection
      patterns: [";&", "|", "$("]

  MEDIUM:
    - type: ssh_brute_force
      threshold: 20
      time_window: 600
    - type: port_scan
      ports_threshold: 5

  LOW:
    - type: http_scan
      paths: ["/wp-admin", "/phpmyadmin", "/admin"]
    - type: ssh_single_attempt
```

### 実装イメージ

- `config/detection_rules.yaml` を起動時に読み込み
- `detection/classifier.py` でルールを評価
- イベントに `severity` フィールドを付与して DB に保存
- Dashboard で severity 別にフィルタ・色分け表示

### 拡張性

- ルールを追加するだけで新しい攻撃タイプに対応可能
- 将来的にはルールの動的リロード（再起動不要）も検討
- MITRE ATT&CK の Technique ID もルールに紐付け可能
