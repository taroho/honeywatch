"""GeoIP 地理情報 API エンドポイント.

送信元 IP（source_ip）を MaxMind GeoLite2 でオンザフライに地理情報（Geo_Location）へ
変換して提供する。地理情報は永続化せず、リクエストのたびに GeoIP_Resolver で都度解決する。

提供エンドポイント:
    - GET /geo/ips/{source_ip}   : 指定 IP の Geo_Location を返す
    - GET /geo/top-ips           : Top IP に Geo_Location を付与して返す
    - GET /geo/country-summary   : 国別の攻撃件数集計を返す

認証必須。フェイルセーフ設計のため、Resolver 利用不可・未解決でも 500 にはせず、
geo 各フィールド null の JSON を返す。
"""

import ipaddress
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Query

from honeywatch.analysis.geoip import CountryAggregator, GeoLocation
from honeywatch.api.deps import AuthUser, DbSession, GeoIPResolverDep
from honeywatch.db.repositories.attack import AttackEventRepository

router = APIRouter(prefix="/geo", tags=["geo"])

# 集計期間文字列 → timedelta のマップ（dashboard.py と同一のロジック）
_PERIOD_MAP: dict[str, timedelta] = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}


def _geo_to_dict(loc: GeoLocation) -> dict[str, object]:
    """GeoLocation を API レスポンス用の dict に変換する共通ヘルパー.

    未解決フィールドは None（JSON では null）としてそのまま出力する。
    全エンドポイントで geo フィールドの形を統一するために使用する。

    Args:
        loc: 変換対象の GeoLocation

    Returns:
        country_code / country_name / region / city / latitude / longitude を
        キーに持つ dict
    """
    return {
        "country_code": loc.country_code,
        "country_name": loc.country_name,
        "region": loc.region,
        "city": loc.city,
        "latitude": loc.latitude,
        "longitude": loc.longitude,
    }


def _parse_iso8601(value: str) -> datetime:
    """ISO 8601 文字列を timezone-aware な datetime にパースする.

    既存の集計処理が UTC aware な datetime を用いるため、naive な入力（タイムゾーン
    情報を持たない文字列）が来た場合は UTC を補って aware に統一する。tz 付きの
    入力はそのまま尊重する。

    Args:
        value: ISO 8601 形式の日時文字列

    Returns:
        timezone-aware（naive の場合は UTC 付与）な datetime

    Raises:
        ValueError: ISO 8601 として解析できない場合（呼び出し側で 400 に変換する）
    """
    parsed = datetime.fromisoformat(value)
    # naive な場合は UTC を付与して aware に統一する
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


@router.get("/ips/{source_ip}")
async def get_ip_geo(
    _user: AuthUser,
    resolver: GeoIPResolverDep,
    source_ip: str,
) -> dict[str, object]:
    """指定 Source_IP の地理情報（Geo_Location）を返す.

    IP 形式を検証し、不正な場合は 400 を返して地理情報は返さない（Requirement 3.5）。
    未解決・Resolver 利用不可の場合でも 500 にはせず、geo 各フィールド null の JSON を
    返す（Requirement 3.2, 3.6）。

    Args:
        source_ip: 解決対象の送信元 IP アドレス

    Returns:
        source_ip と geo（Geo_Location）を含む JSON

    Raises:
        HTTPException: IP 形式が不正な場合（400）
    """
    # IP 形式の検証。不正なら地理情報を返さず 400（Requirement 3.5）
    try:
        ipaddress.ip_address(source_ip)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid IP address") from exc

    # 未解決・Resolver 利用不可でも resolver は未解決 GeoLocation を返す（フェイルセーフ）
    location = resolver.resolve(source_ip)

    return {
        "source_ip": source_ip,
        "geo": _geo_to_dict(location),
    }


@router.get("/top-ips")
async def get_geo_top_ips(
    _user: AuthUser,
    db: DbSession,
    resolver: GeoIPResolverDep,
    limit: int = Query(default=10, ge=1, le=100),
    period: str = Query(default="24h", pattern="^(1h|6h|24h|7d)$"),
) -> dict[str, object]:
    """攻撃数の多い送信元 IP ランキングに Geo_Location を付与して返す.

    既存の dashboard/top-ips と同じ集計結果に、各エントリの geo を付与する。
    件数降順は get_top_ips が担保し、最大件数は limit（1〜100）で担保する
    （Requirement 3.3, 3.7）。未解決 IP の geo は各フィールド null となる。

    Args:
        limit: 取得件数（1〜100、既定 10）
        period: 集計期間（1h/6h/24h/7d、既定 24h）

    Returns:
        各エントリに geo を付与した Top IP ランキングの JSON
    """
    now = datetime.now(UTC)
    since = now - _PERIOD_MAP[period]

    repo = AttackEventRepository(db)
    ips = await repo.get_top_ips(since=since, until=now, limit=limit)

    entries: list[dict[str, object]] = []
    for ip in ips:
        source_ip = ip["source_ip"]
        first_seen = ip["first_seen"]
        last_seen = ip["last_seen"]
        location = resolver.resolve(str(source_ip))
        entries.append(
            {
                "source_ip": source_ip,
                "event_count": ip["event_count"],
                # datetime は isoformat 文字列に、None はそのまま null に
                "first_seen": first_seen.isoformat()
                if isinstance(first_seen, datetime)
                else None,
                "last_seen": last_seen.isoformat()
                if isinstance(last_seen, datetime)
                else None,
                "geo": _geo_to_dict(location),
            }
        )

    return {"ips": entries}


@router.get("/country-summary")
async def get_country_summary(
    _user: AuthUser,
    db: DbSession,
    resolver: GeoIPResolverDep,
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
) -> dict[str, object]:
    """国別の攻撃件数集計を返す.

    期間パラメータ（ISO 8601）で対象を絞り込み、IP 単位の件数集計を国コード単位に
    再集計する。両方未指定なら全期間を対象とする（Requirement 5.5）。指定時は両端を
    含む（Requirement 5.6）。並び順・件数上限（最大 1000）・未解決 IP の UNKNOWN 合算は
    CountryAggregator.aggregate が担保する（Requirement 5.2, 5.3, 5.9）。

    Args:
        start: 集計開始日時（ISO 8601、任意）
        end: 集計終了日時（ISO 8601、任意）

    Returns:
        countries（CountryCount の一覧）を含む JSON。対象 0 件なら空リスト。

    Raises:
        HTTPException: start/end が ISO 8601 でない、または start > end の場合（400）。
            この場合、集計は行わず既存データを変更しない（Requirement 5.7）。
    """
    # 期間パラメータのパース。ISO 8601 でなければ 400（Requirement 5.7）
    since: datetime | None = None
    until: datetime | None = None
    if start is not None:
        try:
            since = _parse_iso8601(start)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail="Invalid ISO 8601 datetime for 'start'"
            ) from exc
    if end is not None:
        try:
            until = _parse_iso8601(end)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail="Invalid ISO 8601 datetime for 'end'"
            ) from exc

    # start > end は不正（Requirement 5.7）。両方指定時のみ比較する。
    if since is not None and until is not None and since > until:
        raise HTTPException(status_code=400, detail="'start' must not be after 'end'")

    repo = AttackEventRepository(db)
    ip_counts = await repo.get_ip_counts(since=since, until=until)

    # 国コード単位に再集計（並び順・上限・UNKNOWN 合算は aggregate が担保）
    countries = CountryAggregator.aggregate(ip_counts, resolver, max_countries=1000)

    return {
        "countries": [
            {"country_code": cc.country_code, "count": cc.count} for cc in countries
        ]
    }
