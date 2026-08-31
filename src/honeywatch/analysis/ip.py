"""IP 分析・Risk Score 算出.

送信元 IP 単位の攻撃履歴を集約し、危険度（Risk Score）を算出する。
Risk Score は攻撃頻度・攻撃タイプの多様性・Severity から 0〜100 で算出する。
"""

from dataclasses import dataclass

from honeywatch.detection.classifier import (
    SEVERITY_HIGH,
    SEVERITY_LOW,
    SEVERITY_MEDIUM,
)

# Severity ごとのスコア寄与（最大値を採用）
_SEVERITY_SCORE = {
    SEVERITY_HIGH: 30,
    SEVERITY_MEDIUM: 15,
    SEVERITY_LOW: 5,
}

# 各スコア要素の上限
_FREQUENCY_SCORE_MAX = 40
_DIVERSITY_SCORE_MAX = 30
_DIVERSITY_SCORE_PER_TYPE = 10

# 頻度スコアの基準（この件数で上限に達する）
_FREQUENCY_SATURATION = 200


@dataclass
class IPProfile:
    """送信元 IP のプロファイル（分析結果）."""

    source_ip: str
    first_seen: str | None
    last_seen: str | None
    total_events: int
    attack_types: list[str]
    risk_score: int
    risk_level: str


class RiskScorer:
    """Risk Score を算出する.

    算出式:
        risk_score = min(100, 頻度スコア + 多様性スコア + Severity スコア)

    - 頻度スコア: イベント数に比例（0〜40）
    - 多様性スコア: 攻撃タイプ数 × 10（最大30）
    - Severity スコア: 観測された最大 Severity（HIGH=30 / MEDIUM=15 / LOW=5）
    """

    @staticmethod
    def calculate(
        total_events: int,
        attack_types: list[str],
        severities: list[str],
    ) -> int:
        """Risk Score を算出する（0〜100）.

        Args:
            total_events: 該当 IP の総イベント数
            attack_types: 観測された攻撃タイプのリスト
            severities: 観測された Severity のリスト

        Returns:
            0〜100 の Risk Score
        """
        # 頻度スコア（0〜40）: イベント数に比例、上限で飽和
        frequency_score = min(
            _FREQUENCY_SCORE_MAX,
            int(total_events / _FREQUENCY_SATURATION * _FREQUENCY_SCORE_MAX),
        )

        # 多様性スコア（0〜30）: 異なる攻撃タイプ数 × 10
        distinct_types = len(set(attack_types))
        diversity_score = min(
            _DIVERSITY_SCORE_MAX,
            distinct_types * _DIVERSITY_SCORE_PER_TYPE,
        )

        # Severity スコア（最大値を採用）
        severity_score = max(
            (_SEVERITY_SCORE.get(s, 0) for s in severities),
            default=0,
        )

        return min(100, frequency_score + diversity_score + severity_score)

    @staticmethod
    def to_risk_level(score: int) -> str:
        """Risk Score を HIGH / MEDIUM / LOW のレベルに変換する.

        Args:
            score: Risk Score（0〜100）

        Returns:
            リスクレベル
        """
        if score >= 70:
            return SEVERITY_HIGH
        if score >= 40:
            return SEVERITY_MEDIUM
        return SEVERITY_LOW


class IPAnalyzer:
    """IP プロファイルを集約する.

    Repository から取得した集計データを IPProfile に組み立て、
    Risk Score を付与する。
    """

    @staticmethod
    def build_profile(
        source_ip: str,
        first_seen: str | None,
        last_seen: str | None,
        total_events: int,
        attack_types: list[str],
        severities: list[str],
    ) -> IPProfile:
        """集計データから IP プロファイルを構築する.

        Args:
            source_ip: 送信元 IP
            first_seen: 初回観測時刻（ISO 文字列）
            last_seen: 最終観測時刻（ISO 文字列）
            total_events: 総イベント数
            attack_types: 観測された攻撃タイプ
            severities: 観測された Severity

        Returns:
            Risk Score を付与した IPProfile
        """
        risk_score = RiskScorer.calculate(total_events, attack_types, severities)
        risk_level = RiskScorer.to_risk_level(risk_score)

        return IPProfile(
            source_ip=source_ip,
            first_seen=first_seen,
            last_seen=last_seen,
            total_events=total_events,
            # 重複を除いた攻撃タイプ一覧
            attack_types=sorted(set(attack_types)),
            risk_score=risk_score,
            risk_level=risk_level,
        )
