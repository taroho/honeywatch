"""Dashboard API エンドポイント.

サマリー、タイムライン、Top IP ランキングを提供する。
認証必須。
"""

from fastapi import APIRouter, Query

from honeywatch.api.deps import AuthUser, DbSession
from honeywatch.api.period import PERIOD_PATTERN, resolve_period_range
from honeywatch.db.repositories.attack import _MONTH_SENTINEL, AttackEventRepository

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
async def get_dashboard_summary(
    _user: AuthUser,
    db: DbSession,
    period: str = Query(default="24h", pattern=PERIOD_PATTERN),
) -> dict[str, object]:
    """Dashboard サマリーカード用の統計データを返す.

    選択された period の集計対象期間で、攻撃数・ユニーク IP 数・SSH 試行数・
    HTTP 攻撃数を集計する。period 未指定時は既定 ``24h``。``all`` のときは
    下限なし（全期間）となり、``period_start`` は null を返す。

    Args:
        period: 集計期間（1h/6h/24h/7d/1y/all、既定 24h）

    Returns:
        サマリー統計データ
    """
    # period → 集計範囲を共通ヘルパーで解決する（all のとき since=None）
    since, until = resolve_period_range(period)

    repo = AttackEventRepository(db)
    summary = await repo.get_summary(since=since, until=until)

    return {
        # レスポンスキー名は後方互換のため従来のまま維持する
        "attacks_today": summary["total"],
        "unique_ips_today": summary["unique_ips"],
        "ssh_attempts_today": summary["ssh_attempts"],
        "http_attacks_today": summary["http_attacks"],
        # since が None（all）のときは下限なしを表す null を返す
        "period_start": since.isoformat() if since is not None else None,
        "period_end": until.isoformat(),
    }


@router.get("/timeline")
async def get_dashboard_timeline(
    _user: AuthUser,
    db: DbSession,
    period: str = Query(default="24h", pattern=PERIOD_PATTERN),
    interval: str = Query(default="1h", pattern="^(5m|15m|1h)$"),
) -> dict[str, object]:
    """時間帯別の攻撃数を返す（タイムライングラフ用）.

    Args:
        period: 集計期間（1h/6h/24h/7d/1y/all）
        interval: 集計間隔（5m, 15m, 1h）

    Returns:
        タイムラインデータ
    """
    # period → 集計範囲を共通ヘルパーで解決する（all のとき since=None）
    since, until = resolve_period_range(period)

    # 間隔を分に変換
    interval_map: dict[str, int] = {
        "5m": 5,
        "15m": 15,
        "1h": 60,
    }
    interval_minutes = interval_map[interval]

    # 1y / all は暦月単位で集計する（区間数を月数に抑える）。
    # interval 指定によらず月粒度（番兵値）を用いる。
    if period in ("1y", "all"):
        interval_minutes = _MONTH_SENTINEL

    repo = AttackEventRepository(db)
    timeline = await repo.get_timeline(
        since=since,
        until=until,
        interval_minutes=interval_minutes,
    )

    return {"timeline": timeline}


@router.get("/top-ips")
async def get_dashboard_top_ips(
    _user: AuthUser,
    db: DbSession,
    limit: int = Query(default=10, ge=1, le=100),
    period: str = Query(default="24h", pattern=PERIOD_PATTERN),
) -> dict[str, object]:
    """攻撃数の多い送信元 IP ランキングを返す.

    Args:
        limit: 取得件数
        period: 集計期間（1h/6h/24h/7d/1y/all）

    Returns:
        IP ランキングデータ
    """
    # period → 集計範囲を共通ヘルパーで解決する（all のとき since=None）
    since, until = resolve_period_range(period)

    repo = AttackEventRepository(db)
    ips = await repo.get_top_ips(since=since, until=until, limit=limit)

    return {"ips": ips}
