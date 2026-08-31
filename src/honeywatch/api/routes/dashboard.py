"""Dashboard API エンドポイント.

サマリー、タイムライン、Top IP ランキングを提供する。
認証必須。
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query

from honeywatch.api.deps import AuthUser, DbSession
from honeywatch.db.repositories.attack import AttackEventRepository

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
async def get_dashboard_summary(
    _user: AuthUser,
    db: DbSession,
) -> dict[str, object]:
    """Dashboard サマリーカード用の統計データを返す.

    本日の攻撃数、ユニーク IP 数、SSH 試行数、HTTP 攻撃数を集計する。

    Returns:
        サマリー統計データ
    """
    now = datetime.now(UTC)
    period_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    period_end = now

    repo = AttackEventRepository(db)
    summary = await repo.get_summary(since=period_start, until=period_end)

    return {
        "attacks_today": summary["total"],
        "unique_ips_today": summary["unique_ips"],
        "ssh_attempts_today": summary["ssh_attempts"],
        "http_attacks_today": summary["http_attacks"],
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
    }


@router.get("/timeline")
async def get_dashboard_timeline(
    _user: AuthUser,
    db: DbSession,
    period: str = Query(default="24h", pattern="^(1h|6h|24h|7d)$"),
    interval: str = Query(default="1h", pattern="^(5m|15m|1h)$"),
) -> dict[str, object]:
    """時間帯別の攻撃数を返す（タイムライングラフ用）.

    Args:
        period: 集計期間（1h, 6h, 24h, 7d）
        interval: 集計間隔（5m, 15m, 1h）

    Returns:
        タイムラインデータ
    """
    now = datetime.now(UTC)

    # 期間を計算
    period_map: dict[str, timedelta] = {
        "1h": timedelta(hours=1),
        "6h": timedelta(hours=6),
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
    }
    since = now - period_map[period]

    # 間隔を分に変換
    interval_map: dict[str, int] = {
        "5m": 5,
        "15m": 15,
        "1h": 60,
    }
    interval_minutes = interval_map[interval]

    repo = AttackEventRepository(db)
    timeline = await repo.get_timeline(
        since=since,
        until=now,
        interval_minutes=interval_minutes,
    )

    return {"timeline": timeline}


@router.get("/top-ips")
async def get_dashboard_top_ips(
    _user: AuthUser,
    db: DbSession,
    limit: int = Query(default=10, ge=1, le=100),
    period: str = Query(default="24h", pattern="^(1h|6h|24h|7d)$"),
) -> dict[str, object]:
    """攻撃数の多い送信元 IP ランキングを返す.

    Args:
        limit: 取得件数
        period: 集計期間

    Returns:
        IP ランキングデータ
    """
    now = datetime.now(UTC)

    period_map: dict[str, timedelta] = {
        "1h": timedelta(hours=1),
        "6h": timedelta(hours=6),
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
    }
    since = now - period_map[period]

    repo = AttackEventRepository(db)
    ips = await repo.get_top_ips(since=since, until=now, limit=limit)

    return {"ips": ips}
