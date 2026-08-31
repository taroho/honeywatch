"""攻撃分類エンジン.

AttackEvent を攻撃タイプに分類し、Severity を判定する。
判定基準は DetectionRules（YAML から読み込んだルール）に従う。
"""

from dataclasses import dataclass, field

from honeywatch.collector.events import AttackEvent
from honeywatch.core.logging import get_logger
from honeywatch.detection.patterns import DetectionRules

logger = get_logger(__name__)


# 攻撃タイプ定数
ATTACK_BRUTE_FORCE = "brute_force"
ATTACK_PORT_SCAN = "port_scan"
ATTACK_HTTP_SCAN = "http_scan"
ATTACK_CREDENTIAL = "credential_attack"
ATTACK_COMMAND_INJECTION = "command_injection"
ATTACK_SUSPICIOUS = "suspicious_request"

# Severity 定数
SEVERITY_HIGH = "HIGH"
SEVERITY_MEDIUM = "MEDIUM"
SEVERITY_LOW = "LOW"


@dataclass
class IPContext:
    """分類に必要な送信元 IP の文脈情報.

    Brute Force / Port Scan の判定には「時間窓内の試行回数」や
    「接続した宛先ポートの種類数」が必要なため、それらを保持する。
    Redis のカウンタから構築される（Task 4）。
    """

    # 時間窓内の同一 IP からの試行回数
    recent_attempts: int = 0
    # 時間窓内にこの IP が接続した宛先ポートの集合
    distinct_ports: set[int] = field(default_factory=set)


@dataclass
class ClassificationResult:
    """分類結果."""

    attack_type: str
    severity: str


class AttackClassifier:
    """攻撃イベントを分類し Severity を判定するエンジン."""

    def __init__(self, rules: DetectionRules) -> None:
        """分類エンジンを初期化する.

        Args:
            rules: 検知ルール（YAML から読み込み済み）
        """
        self._rules = rules
        self._severity_evaluator = SeverityEvaluator(rules)

    def classify(self, event: AttackEvent, context: IPContext) -> ClassificationResult:
        """イベントを分類し、attack_type と severity を判定する.

        判定は優先度の高い順に評価し、最初にマッチしたタイプを採用する:
        command_injection > credential_attack > brute_force
        > port_scan > http_scan > suspicious_request

        Args:
            event: 分類対象の攻撃イベント
            context: 送信元 IP の文脈情報（試行回数・ポート等）

        Returns:
            分類結果（attack_type + severity）
        """
        attack_type = self._determine_attack_type(event, context)
        severity = self._severity_evaluator.evaluate(attack_type, context)

        logger.debug(
            "classifier.classified",
            event_id=str(event.id),
            attack_type=attack_type,
            severity=severity,
        )

        return ClassificationResult(attack_type=attack_type, severity=severity)

    def _determine_attack_type(self, event: AttackEvent, context: IPContext) -> str:
        """攻撃タイプを判定する（優先度順に評価）."""
        # 1. Command Injection（最優先: 明確な悪意）
        if self._is_command_injection(event):
            return ATTACK_COMMAND_INJECTION

        # 2. Credential Attack（既知の弱い認証情報）
        if self._is_credential_attack(event):
            return ATTACK_CREDENTIAL

        # 3. Brute Force（時間窓内の反復試行）
        if self._is_brute_force(event, context):
            return ATTACK_BRUTE_FORCE

        # 4. Port Scan（複数ポートへの接続）
        if self._is_port_scan(context):
            return ATTACK_PORT_SCAN

        # 5. HTTP Scan（機密パスへのアクセス）
        if self._is_http_scan(event):
            return ATTACK_HTTP_SCAN

        # 6. デフォルト（不審なアクセス）
        return ATTACK_SUSPICIOUS

    def _is_command_injection(self, event: AttackEvent) -> bool:
        """コマンドインジェクションパターンを含むか判定する."""
        patterns = self._rules.attack_types.command_injection.patterns
        if not patterns:
            return False

        # HTTP のパス・ボディを検査対象にする
        targets: list[str] = []
        if event.protocol == "http":
            path = event.raw_data.get("path")
            body = event.raw_data.get("body_preview")
            if isinstance(path, str):
                targets.append(path)
            if isinstance(body, str):
                targets.append(body)

        return any(pattern in target for target in targets for pattern in patterns)

    def _is_credential_attack(self, event: AttackEvent) -> bool:
        """既知の弱いユーザー名/パスワードによる攻撃か判定する."""
        if event.protocol != "ssh":
            return False

        rule = self._rules.attack_types.credential_attack
        username = event.raw_data.get("username")
        password = event.raw_data.get("password")

        username_match = isinstance(username, str) and username in rule.usernames
        password_match = isinstance(password, str) and password in rule.passwords

        return username_match or password_match

    def _is_brute_force(self, event: AttackEvent, context: IPContext) -> bool:
        """時間窓内の反復試行（Brute Force）か判定する."""
        rule = self._rules.attack_types.brute_force
        if event.protocol != rule.protocol:
            return False
        return context.recent_attempts >= rule.min_attempts

    def _is_port_scan(self, context: IPContext) -> bool:
        """複数ポートへの接続（Port Scan）か判定する."""
        rule = self._rules.attack_types.port_scan
        return len(context.distinct_ports) >= rule.min_distinct_ports

    def _is_http_scan(self, event: AttackEvent) -> bool:
        """機密パスへのアクセス（HTTP Scan）か判定する."""
        if event.protocol != "http":
            return False

        rule = self._rules.attack_types.http_scan
        path = event.raw_data.get("path")
        if not isinstance(path, str):
            return False

        # パスがルール定義のいずれかで始まるか
        return any(path.startswith(scan_path) for scan_path in rule.paths)


class SeverityEvaluator:
    """攻撃タイプと文脈から Severity を判定する."""

    def __init__(self, rules: DetectionRules) -> None:
        """Severity 判定器を初期化する.

        Args:
            rules: 検知ルール
        """
        self._rules = rules

    def evaluate(self, attack_type: str, context: IPContext) -> str:
        """Severity を判定する.

        HIGH → MEDIUM → LOW の順に条件を評価し、最初にマッチしたレベルを返す。
        どれにもマッチしない場合は LOW をデフォルトとする。

        Args:
            attack_type: 判定済みの攻撃タイプ
            context: 送信元 IP の文脈情報

        Returns:
            Severity（HIGH / MEDIUM / LOW）
        """
        severity_rules = self._rules.severity_rules

        # 優先度順に評価
        for level, conditions in (
            (SEVERITY_HIGH, severity_rules.HIGH),
            (SEVERITY_MEDIUM, severity_rules.MEDIUM),
            (SEVERITY_LOW, severity_rules.LOW),
        ):
            for condition in conditions:
                if condition.attack_type != attack_type:
                    continue
                # min_attempts が指定されている場合は試行回数をチェック
                if condition.min_attempts is not None:
                    if context.recent_attempts >= condition.min_attempts:
                        return level
                else:
                    return level

        # どのルールにもマッチしない場合は LOW
        return SEVERITY_LOW
