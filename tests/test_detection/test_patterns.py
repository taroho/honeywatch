"""DetectionRuleLoader のユニットテスト.

YAML の読み込み・バリデーション・エラーハンドリングを検証する。
"""

from pathlib import Path

import pytest

from honeywatch.detection.patterns import DetectionRuleLoader, DetectionRules


def test_load_default_rules() -> None:
    """デフォルトの config/detection_rules.yaml を読み込める.

    pytest はプロジェクトルートで実行される前提。
    """
    rules = DetectionRuleLoader.load()
    assert isinstance(rules, DetectionRules)
    # YAML で定義した内容が反映されているか
    assert rules.attack_types.brute_force.min_attempts > 0
    assert len(rules.attack_types.http_scan.paths) > 0


def test_load_custom_rules(tmp_path: Path) -> None:
    """任意のパスのルールファイルを読み込める."""
    rule_file = tmp_path / "rules.yaml"
    rule_file.write_text(
        """
attack_types:
  brute_force:
    protocol: ssh
    min_attempts: 10
    time_window: 300
severity_rules:
  HIGH:
    - attack_type: command_injection
""",
        encoding="utf-8",
    )

    rules = DetectionRuleLoader.load(str(rule_file))
    assert rules.attack_types.brute_force.min_attempts == 10
    assert rules.attack_types.brute_force.time_window == 300
    assert rules.severity_rules.HIGH[0].attack_type == "command_injection"


def test_load_missing_file_raises() -> None:
    """存在しないファイルは FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        DetectionRuleLoader.load("nonexistent/path/rules.yaml")


def test_load_invalid_yaml_raises(tmp_path: Path) -> None:
    """不正な YAML は ValueError."""
    rule_file = tmp_path / "broken.yaml"
    rule_file.write_text("attack_types: [unclosed", encoding="utf-8")

    with pytest.raises(ValueError, match="YAML"):
        DetectionRuleLoader.load(str(rule_file))


def test_load_empty_file_uses_defaults(tmp_path: Path) -> None:
    """空ファイルはデフォルト値で読み込まれる."""
    rule_file = tmp_path / "empty.yaml"
    rule_file.write_text("", encoding="utf-8")

    rules = DetectionRuleLoader.load(str(rule_file))
    assert isinstance(rules, DetectionRules)
    # デフォルト値が入る
    assert rules.attack_types.brute_force.min_attempts == 5
