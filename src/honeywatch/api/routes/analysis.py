"""攻撃分析 API エンドポイント.

攻撃タイプ別集計、IP 詳細プロファイル、Risk Score ランキング、
Severity 別統計を提供する。認証必須。
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query

from honeywatch.analysis.ip import IPAnalyzer, IPProfile
from honeywatch.api.deps import AuthUser, DbSession
from honeywatch.db.repositories.attack import AttackEventRepository, IPAggregate

router = APIRouter(prefix="/analysis", tags=["analysis"])


def _build_profile(agg: IPAggregate) -> IPProfile:
    """IPAggregate から IPProfile を構築するヘルパー."""
    return IPAnalyzer.build_profile(
        source_ip=agg["source_ip"],
        first_seen=agg["first_seen"].isoformat() if agg["first_seen"] else None,
        last_seen=agg["last_seen"].isoformat() if agg["last_seen"] else None,
        total_events=agg["total_events"],
        attack_types=agg["attack_types"],
        severities=agg["severities"],
    )

# 集計期間 → timedelta のマップ
_PERIOD_MAP: dict[str, timedelta] = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}


def _period_to_range(period: str) -> tuple[datetime, datetime]:
    """集計期間文字列を (開始, 終了) の datetime に変換する."""
    now = datetime.now(UTC)
    return now - _PERIOD_MAP[period], now


@router.get("/attack-types")
async def get_attack_types(
    _user: AuthUser,
    db: DbSession,
    period: str = Query(default="24h", pattern="^(1h|6h|24h|7d)$"),
) -> dict[str, object]:
    """攻撃タイプ別の集計を返す.

    Args:
        period: 集計期間（1h/6h/24h/7d）

    Returns:
        攻撃タイプごとの件数
    """
    since, until = _period_to_range(period)
    repo = AttackEventRepository(db)
    counts = await repo.count_by_attack_type(since=since, until=until)
    return {"attack_types": counts}


@router.get("/severity-summary")
async def get_severity_summary(
    _user: AuthUser,
    db: DbSession,
    period: str = Query(default="24h", pattern="^(1h|6h|24h|7d)$"),
) -> dict[str, object]:
    """Severity 別のイベント件数を返す.

    Args:
        period: 集計期間

    Returns:
        Severity 別件数（HIGH / MEDIUM / LOW）
    """
    since, until = _period_to_range(period)
    repo = AttackEventRepository(db)
    summary = await repo.count_by_severity(since=since, until=until)
    # 全レベルを含めて返す（0件のレベルも明示）
    return {
        "severity_summary": {
            "HIGH": summary.get("HIGH", 0),
            "MEDIUM": summary.get("MEDIUM", 0),
            "LOW": summary.get("LOW", 0),
        }
    }


@router.get("/risk-ranking")
async def get_risk_ranking(
    _user: AuthUser,
    db: DbSession,
    limit: int = Query(default=10, ge=1, le=100),
    period: str = Query(default="24h", pattern="^(1h|6h|24h|7d)$"),
) -> dict[str, object]:
    """Risk Score の高い IP ランキングを返す.

    Args:
        limit: 取得件数
        period: 集計期間

    Returns:
        Risk Score 降順の IP ランキング
    """
    since, until = _period_to_range(period)
    repo = AttackEventRepository(db)

    # イベント数上位の候補を多めに取得してから Risk Score で並べ替える
    aggregates = await repo.get_ip_aggregates_for_ranking(
        since=since, until=until, limit=max(limit * 3, 30)
    )

    # 各 IP のプロファイルを構築（Risk Score 算出）
    profiles = [_build_profile(agg) for agg in aggregates]

    # Risk Score 降順にソートして上位 limit 件を返す
    profiles.sort(key=lambda p: p.risk_score, reverse=True)
    top = profiles[:limit]

    return {
        "ranking": [
            {
                "source_ip": p.source_ip,
                "risk_score": p.risk_score,
                "risk_level": p.risk_level,
                "total_events": p.total_events,
                "attack_types": p.attack_types,
            }
            for p in top
        ]
    }


@router.get("/ips/{source_ip}")
async def get_ip_profile(
    _user: AuthUser,
    db: DbSession,
    source_ip: str,
) -> dict[str, object]:
    """指定 IP の詳細プロファイルを返す.

    Args:
        source_ip: 送信元 IP

    Returns:
        IP プロファイル（攻撃履歴 + Risk Score）

    Raises:
        HTTPException: 該当 IP のイベントが存在しない場合（404）
    """
    repo = AttackEventRepository(db)
    agg = await repo.get_ip_aggregate(source_ip)

    if agg is None:
        raise HTTPException(status_code=404, detail="IP not found")

    profile = _build_profile(agg)

    return {
        "source_ip": profile.source_ip,
        "first_seen": profile.first_seen,
        "last_seen": profile.last_seen,
        "total_events": profile.total_events,
        "attack_types": profile.attack_types,
        "risk_score": profile.risk_score,
        "risk_level": profile.risk_level,
    }
