"""AttackClassifier / SeverityEvaluator のユニットテスト.

分類ロジックと Severity 判定が Detection Rule 通りに動作するか検証する。
Redis / DB に依存しない純粋ロジックのテスト。
"""

import pytest

from honeywatch.collector.events import AttackEvent
from honeywatch.detection.classifier import (
    ATTACK_BRUTE_FORCE,
    ATTACK_COMMAND_INJECTION,
    ATTACK_CREDENTIAL,
    ATTACK_HTTP_SCAN,
    ATTACK_PORT_SCAN,
    ATTACK_SUSPICIOUS,
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
    AttackClassifier,
    IPContext,
    SeverityEvaluator,
)
from honeywatch.detection.patterns import (
    AttackTypeRules,
    BruteForceRule,
    CommandInjectionRule,
    CredentialAttackRule,
    DetectionRules,
    HTTPScanRule,
    PortScanRule,
    SeverityCondition,
    SeverityRules,
)


@pytest.fixture
def rules() -> DetectionRules:
    """テスト用の Detection Rule を構築する（YAML と同等の内容）."""
    return DetectionRules(
        attack_types=AttackTypeRules(
            brute_force=BruteForceRule(protocol="ssh", min_attempts=5, time_window=600),
            port_scan=PortScanRule(min_distinct_ports=3, time_window=300),
            http_scan=HTTPScanRule(protocol="http", paths=["/admin", "/wp-admin"]),
            credential_attack=CredentialAttackRule(
                protocol="ssh",
                usernames=["root", "admin"],
                passwords=["123456", "password"],
            ),
            command_injection=CommandInjectionRule(patterns=[";", "|", "$("]),
        ),
        severity_rules=SeverityRules(
            HIGH=[
                SeverityCondition(attack_type="brute_force", min_attempts=100),
                SeverityCondition(attack_type="command_injection"),
            ],
            MEDIUM=[
                SeverityCondition(attack_type="brute_force", min_attempts=20),
                SeverityCondition(attack_type="port_scan"),
                SeverityCondition(attack_type="credential_attack"),
            ],
            LOW=[
                SeverityCondition(attack_type="http_scan"),
                SeverityCondition(attack_type="brute_force"),
                SeverityCondition(attack_type="suspicious_request"),
            ],
        ),
    )


@pytest.fixture
def classifier(rules: DetectionRules) -> AttackClassifier:
    """テスト用の分類器."""
    return AttackClassifier(rules)


def _ssh_event(username: str = "guest", password: str = "guest") -> AttackEvent:
    """SSH イベントを生成するヘルパー."""
    return AttackEvent(
        source_ip="203.0.113.1",
        source_port=54321,
        destination_port=2222,
        protocol="ssh",
        event_type="ssh_login_attempt",
        raw_data={"username": username, "password": password},
    )


def _http_event(path: str = "/", body: str | None = None) -> AttackEvent:
    """HTTP イベントを生成するヘルパー."""
    raw: dict[str, object] = {"path": path, "method": "GET"}
    if body is not None:
        raw["body_preview"] = body
    return AttackEvent(
        source_ip="203.0.113.2",
        source_port=54321,
        destination_port=8080,
        protocol="http",
        event_type="http_request",
        raw_data=raw,
    )


# === 攻撃タイプ判定 ===


def test_command_injection_detected(classifier: AttackClassifier) -> None:
    """コマンドインジェクションパターンを検出する."""
    event = _http_event(path="/api?cmd=ls;cat /etc/passwd")
    result = classifier.classify(event, IPContext())
    assert result.attack_type == ATTACK_COMMAND_INJECTION


def test_command_injection_in_body(classifier: AttackClassifier) -> None:
    """リクエストボディ内のインジェクションも検出する."""
    event = _http_event(path="/upload", body="data=$(whoami)")
    result = classifier.classify(event, IPContext())
    assert result.attack_type == ATTACK_COMMAND_INJECTION


def test_credential_attack_by_username(classifier: AttackClassifier) -> None:
    """既知の弱いユーザー名を検出する."""
    event = _ssh_event(username="root", password="somepass")
    result = classifier.classify(event, IPContext())
    assert result.attack_type == ATTACK_CREDENTIAL


def test_credential_attack_by_password(classifier: AttackClassifier) -> None:
    """既知の弱いパスワードを検出する."""
    event = _ssh_event(username="someuser", password="123456")
    result = classifier.classify(event, IPContext())
    assert result.attack_type == ATTACK_CREDENTIAL


def test_brute_force_detected(classifier: AttackClassifier) -> None:
    """時間窓内の反復試行を Brute Force と判定する."""
    # 弱い認証情報ではないユーザー名/パスワードで試行回数のみ多い
    event = _ssh_event(username="guest", password="xyz")
    context = IPContext(recent_attempts=10)
    result = classifier.classify(event, context)
    assert result.attack_type == ATTACK_BRUTE_FORCE


def test_brute_force_below_threshold_is_suspicious(
    classifier: AttackClassifier,
) -> None:
    """閾値未満の試行は Brute Force とみなさない."""
    event = _ssh_event(username="guest", password="xyz")
    context = IPContext(recent_attempts=2)
    result = classifier.classify(event, context)
    assert result.attack_type == ATTACK_SUSPICIOUS


def test_port_scan_detected(classifier: AttackClassifier) -> None:
    """複数ポートへの接続を Port Scan と判定する."""
    event = _http_event(path="/")
    context = IPContext(distinct_ports={22, 80, 443, 8080})
    result = classifier.classify(event, context)
    assert result.attack_type == ATTACK_PORT_SCAN


def test_http_scan_detected(classifier: AttackClassifier) -> None:
    """機密パスへのアクセスを HTTP Scan と判定する."""
    event = _http_event(path="/admin/login")
    result = classifier.classify(event, IPContext())
    assert result.attack_type == ATTACK_HTTP_SCAN


def test_suspicious_request_default(classifier: AttackClassifier) -> None:
    """どのルールにも該当しない場合は suspicious_request."""
    event = _http_event(path="/")
    result = classifier.classify(event, IPContext())
    assert result.attack_type == ATTACK_SUSPICIOUS


def test_priority_command_injection_over_http_scan(
    classifier: AttackClassifier,
) -> None:
    """コマンドインジェクションは HTTP Scan より優先される."""
    # /admin（http_scan 該当）かつ ; を含む（command_injection 該当）
    event = _http_event(path="/admin;rm -rf")
    result = classifier.classify(event, IPContext())
    assert result.attack_type == ATTACK_COMMAND_INJECTION


# === Severity 判定 ===


def test_severity_high_command_injection(rules: DetectionRules) -> None:
    """コマンドインジェクションは HIGH."""
    evaluator = SeverityEvaluator(rules)
    assert evaluator.evaluate(ATTACK_COMMAND_INJECTION, IPContext()) == SEVERITY_HIGH


def test_severity_high_brute_force_many_attempts(rules: DetectionRules) -> None:
    """100回以上の Brute Force は HIGH."""
    evaluator = SeverityEvaluator(rules)
    context = IPContext(recent_attempts=150)
    assert evaluator.evaluate(ATTACK_BRUTE_FORCE, context) == SEVERITY_HIGH


def test_severity_medium_brute_force(rules: DetectionRules) -> None:
    """20〜99回の Brute Force は MEDIUM."""
    evaluator = SeverityEvaluator(rules)
    context = IPContext(recent_attempts=30)
    assert evaluator.evaluate(ATTACK_BRUTE_FORCE, context) == SEVERITY_MEDIUM


def test_severity_low_brute_force_few_attempts(rules: DetectionRules) -> None:
    """20回未満の Brute Force は LOW."""
    evaluator = SeverityEvaluator(rules)
    context = IPContext(recent_attempts=10)
    assert evaluator.evaluate(ATTACK_BRUTE_FORCE, context) == SEVERITY_LOW


def test_severity_medium_credential_attack(rules: DetectionRules) -> None:
    """Credential Attack は MEDIUM."""
    evaluator = SeverityEvaluator(rules)
    assert evaluator.evaluate(ATTACK_CREDENTIAL, IPContext()) == SEVERITY_MEDIUM


def test_severity_low_http_scan(rules: DetectionRules) -> None:
    """HTTP Scan は LOW."""
    evaluator = SeverityEvaluator(rules)
    assert evaluator.evaluate(ATTACK_HTTP_SCAN, IPContext()) == SEVERITY_LOW
