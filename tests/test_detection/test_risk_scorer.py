"""RiskScorer のユニットテスト.

Risk Score 算出とレベル変換が仕様通りか検証する。
"""

from honeywatch.analysis.ip import IPAnalyzer, RiskScorer

# === Risk Score 算出 ===


def test_score_zero_for_no_events() -> None:
    """イベントなしはスコア 0."""
    score = RiskScorer.calculate(total_events=0, attack_types=[], severities=[])
    assert score == 0


def test_score_within_range() -> None:
    """スコアは常に 0〜100 に収まる."""
    score = RiskScorer.calculate(
        total_events=100000,
        attack_types=["brute_force", "port_scan", "http_scan", "credential_attack"],
        severities=["HIGH", "MEDIUM", "LOW"],
    )
    assert 0 <= score <= 100


def test_score_clamped_at_100() -> None:
    """大量イベント + 多様な攻撃 + HIGH でも 100 を超えない."""
    score = RiskScorer.calculate(
        total_events=100000,
        attack_types=["a", "b", "c", "d", "e", "f"],
        severities=["HIGH"],
    )
    assert score == 100


def test_frequency_contributes_to_score() -> None:
    """イベント数が多いほどスコアが高い."""
    low = RiskScorer.calculate(total_events=10, attack_types=["brute_force"], severities=["LOW"])
    high = RiskScorer.calculate(
        total_events=200, attack_types=["brute_force"], severities=["LOW"]
    )
    assert high > low


def test_diversity_contributes_to_score() -> None:
    """攻撃タイプが多様なほどスコアが高い."""
    single = RiskScorer.calculate(
        total_events=10, attack_types=["brute_force"], severities=["LOW"]
    )
    diverse = RiskScorer.calculate(
        total_events=10,
        attack_types=["brute_force", "port_scan", "http_scan"],
        severities=["LOW"],
    )
    assert diverse > single


def test_severity_uses_max() -> None:
    """Severity スコアは最大値を採用する."""
    # HIGH を含む方がスコアが高い
    with_high = RiskScorer.calculate(
        total_events=10, attack_types=["brute_force"], severities=["LOW", "HIGH"]
    )
    only_low = RiskScorer.calculate(
        total_events=10, attack_types=["brute_force"], severities=["LOW"]
    )
    assert with_high > only_low


def test_duplicate_attack_types_counted_once() -> None:
    """同じ攻撃タイプの重複は多様性スコアに影響しない."""
    dup = RiskScorer.calculate(
        total_events=10,
        attack_types=["brute_force", "brute_force", "brute_force"],
        severities=["LOW"],
    )
    single = RiskScorer.calculate(
        total_events=10, attack_types=["brute_force"], severities=["LOW"]
    )
    assert dup == single


# === レベル変換 ===


def test_risk_level_high() -> None:
    """70 以上は HIGH."""
    assert RiskScorer.to_risk_level(70) == "HIGH"
    assert RiskScorer.to_risk_level(100) == "HIGH"


def test_risk_level_medium() -> None:
    """40〜69 は MEDIUM."""
    assert RiskScorer.to_risk_level(40) == "MEDIUM"
    assert RiskScorer.to_risk_level(69) == "MEDIUM"


def test_risk_level_low() -> None:
    """40 未満は LOW."""
    assert RiskScorer.to_risk_level(0) == "LOW"
    assert RiskScorer.to_risk_level(39) == "LOW"


# === IPAnalyzer ===


def test_build_profile_dedupes_attack_types() -> None:
    """プロファイルの攻撃タイプは重複除去・ソートされる."""
    profile = IPAnalyzer.build_profile(
        source_ip="203.0.113.1",
        first_seen="2026-08-28T10:00:00Z",
        last_seen="2026-08-28T14:00:00Z",
        total_events=5,
        attack_types=["http_scan", "brute_force", "brute_force"],
        severities=["LOW", "MEDIUM"],
    )
    assert profile.attack_types == ["brute_force", "http_scan"]
    assert profile.source_ip == "203.0.113.1"
    assert 0 <= profile.risk_score <= 100
    assert profile.risk_level in ("HIGH", "MEDIUM", "LOW")
