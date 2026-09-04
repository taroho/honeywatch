"""期間（period）変換の共通ヘルパー.

Dashboard の統一期間セレクタが受け付ける period 文字列
（``1h`` / ``6h`` / ``24h`` / ``7d`` / ``1y`` / ``all``）を、
集計に用いる ``(since, until)`` の範囲へ変換する処理を集約する。

period 対応の全ルート（dashboard / analysis / geo）がこのモジュールを
import して共有することで、期間定義の重複を排除する。
"""

from datetime import UTC, datetime, timedelta

# 受理する period の正規表現（全ルートで共有する定数）。
# FastAPI の Query(pattern=...) に渡し、不正値は 422 で拒否される。
PERIOD_PATTERN = "^(1h|6h|24h|7d|1y|all)$"

# period → timedelta のマップ（"all" は下限なしのためマップに含めない）。
# 1h/6h/24h/7d は従来値を維持し、1y は直近 365 日とする（Requirement 3.1）。
_PERIOD_MAP: dict[str, timedelta] = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "1y": timedelta(days=365),  # 直近365日（Requirement 3.1）
}


def resolve_period_range(period: str) -> tuple[datetime | None, datetime]:
    """period 文字列を集計範囲 ``(since, until)`` に変換する.

    ``until`` は常に要求受信時刻（``now``）とする。``since`` は period が
    ``all`` のとき ``None``（下限なし＝全期間）、それ以外は ``now`` から
    対応する ``timedelta`` を差し引いた時刻とする。

    Args:
        period: 受理済みの period 文字列。呼び出し側で ``PERIOD_PATTERN``
            による検証（FastAPI の Query pattern）を通過している前提。
            ``1h`` / ``6h`` / ``24h`` / ``7d`` / ``1y`` / ``all`` のいずれか。

    Returns:
        ``(since, until)`` のタプル。``since`` は ``all`` のとき ``None``、
        それ以外は ``until`` から当該期間だけ遡った時刻。``until`` は
        要求受信時刻（``now``）。
    """
    now = datetime.now(UTC)
    if period == "all":
        return None, now
    return now - _PERIOD_MAP[period], now
