"""Detection Rule（攻撃検知ルール）の定義とローダー.

config/detection_rules.yaml を読み込み、Pydantic で型安全に扱う。
起動時にバリデーションを行い、不正なルールがあれば例外を送出する。
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from honeywatch.core.logging import get_logger

logger = get_logger(__name__)

# デフォルトのルールファイルパス（プロジェクトルート基準）
DEFAULT_RULES_PATH = "config/detection_rules.yaml"


class BruteForceRule(BaseModel):
    """Brute Force 判定ルール."""

    protocol: str = "ssh"
    min_attempts: int = Field(default=5, ge=1)
    time_window: int = Field(default=600, ge=1)


class PortScanRule(BaseModel):
    """Port Scan 判定ルール."""

    min_distinct_ports: int = Field(default=3, ge=1)
    time_window: int = Field(default=300, ge=1)


class HTTPScanRule(BaseModel):
    """HTTP Scan 判定ルール."""

    protocol: str = "http"
    paths: list[str] = Field(default_factory=list)


class CredentialAttackRule(BaseModel):
    """Credential Attack 判定ルール."""

    protocol: str = "ssh"
    usernames: list[str] = Field(default_factory=list)
    passwords: list[str] = Field(default_factory=list)


class CommandInjectionRule(BaseModel):
    """Command Injection 判定ルール."""

    patterns: list[str] = Field(default_factory=list)


class AttackTypeRules(BaseModel):
    """攻撃タイプ別の判定ルール集合."""

    brute_force: BruteForceRule = Field(default_factory=BruteForceRule)
    port_scan: PortScanRule = Field(default_factory=PortScanRule)
    http_scan: HTTPScanRule = Field(default_factory=HTTPScanRule)
    credential_attack: CredentialAttackRule = Field(default_factory=CredentialAttackRule)
    command_injection: CommandInjectionRule = Field(default_factory=CommandInjectionRule)


class SeverityCondition(BaseModel):
    """Severity 判定の1条件.

    attack_type がマッチし、min_attempts が指定されている場合は
    試行回数がその値以上のときにマッチする。
    """

    attack_type: str
    min_attempts: int | None = None


class SeverityRules(BaseModel):
    """Severity レベル別の判定条件.

    各レベルは条件のリストを持ち、いずれかにマッチすればそのレベルとなる。
    HIGH → MEDIUM → LOW の順に評価する。
    """

    HIGH: list[SeverityCondition] = Field(default_factory=list)
    MEDIUM: list[SeverityCondition] = Field(default_factory=list)
    LOW: list[SeverityCondition] = Field(default_factory=list)


class DetectionRules(BaseModel):
    """検知ルール全体."""

    attack_types: AttackTypeRules = Field(default_factory=AttackTypeRules)
    severity_rules: SeverityRules = Field(default_factory=SeverityRules)


class DetectionRuleLoader:
    """Detection Rule の読み込み・管理を行うローダー."""

    @staticmethod
    def load(path: str | None = None) -> DetectionRules:
        """YAML ファイルからルールを読み込む.

        Args:
            path: ルールファイルのパス。None の場合はデフォルトパスを使用。

        Returns:
            バリデーション済みの DetectionRules

        Raises:
            FileNotFoundError: ファイルが存在しない場合
            ValueError: YAML パースまたはバリデーションに失敗した場合
        """
        rules_path = Path(path or DEFAULT_RULES_PATH)

        if not rules_path.exists():
            raise FileNotFoundError(f"Detection rule ファイルが見つかりません: {rules_path}")

        try:
            with rules_path.open(encoding="utf-8") as f:
                raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Detection rule の YAML パースに失敗しました: {e}") from e

        if raw is None:
            raw = {}

        try:
            rules = DetectionRules.model_validate(raw)
        except Exception as e:
            raise ValueError(f"Detection rule のバリデーションに失敗しました: {e}") from e

        logger.info("detection_rules.loaded", path=str(rules_path))
        return rules
