"""GeoIP API エンドポイント（api/routes/geo.py）のプロパティテスト・ユニットテスト.

design.md「Correctness Properties」の Property 5・Property 9 を Hypothesis で検証し、
`/geo/ips/{ip}` / `/geo/top-ips` / `/geo/country-summary` の正常系・異常系を
例示（ユニット）テストで検証する。

テスト方針（design.md「Testing Strategy」に準拠）:
    実 DB・実 .mmdb には依存させない。FastAPI の ``app.dependency_overrides`` と
    ``app.state`` を使ってモックを注入する。

    - 認証: ``verify_credentials`` を override して認証を無効化する。
    - DB: ``get_db`` を最小のダミー async generator に差し替える。実際の Repository の
      戻り値は ``AttackEventRepository`` 自体を ``patch`` してモックで制御するため、
      get_db が返すセッションは使われない（None で十分）。
    - Resolver: ``app.state.geoip_resolver`` にモック Resolver を直接差し込む。

    lifespan の注意点:
        ``with TestClient(app) as client:`` を使うと lifespan（startup）が走り、
        実際の ``GeoIPResolver.load`` が ``app.state.geoip_resolver`` を上書きしてしまう。
        本テストでは lifespan を回避するため、TestClient を ``with`` なしで生成する
        （startup/shutdown が走らない）。その上で fixture が
        ``app.state.geoip_resolver`` にモックを直接セットする。
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from honeywatch.analysis.geoip import GeoLocation
from honeywatch.api.deps import get_db, verify_credentials
from honeywatch.api.main import app

# GeoIP API のベースパス（main.py で prefix="/api/v1"、router で prefix="/geo"）
_BASE = "/api/v1/geo"


# =====================================================================
# ヘルパー
# =====================================================================


def _make_resolver(ip_to_location: dict[str, GeoLocation]) -> MagicMock:
    """resolve をラップしたモック Resolver を生成する.

    ``ip_to_location`` に含まれる IP は対応する GeoLocation を返し、含まれない IP は
    未解決（全 None）を返す。DB／.mmdb には依存しない。

    Args:
        ip_to_location: IP → GeoLocation のマッピング

    Returns:
        ``resolve(ip)`` を持つ ``MagicMock``（呼び出し検証にも使える）
    """

    def _resolve(ip: str) -> GeoLocation:
        return ip_to_location.get(ip, GeoLocation.unresolved())

    resolver = MagicMock()
    resolver.resolve.side_effect = _resolve
    return resolver


def _resolved_location(country_code: str) -> GeoLocation:
    """テスト用の解決済み GeoLocation を生成する."""
    return GeoLocation(
        country_code=country_code,
        country_name=f"Country {country_code}",
        region="Region",
        city="City",
        latitude=35.0,
        longitude=139.0,
    )


async def _dummy_get_db() -> Any:
    """get_db を差し替えるダミー依存性.

    Repository を patch でモックするため、セッションの実体は使われない。async
    generator として ``None`` を yield するだけで十分。
    """
    yield None


@pytest.fixture
def client() -> Iterator[TestClient]:
    """認証無効・ダミー DB を注入した TestClient を提供する.

    lifespan を走らせないため ``with`` を使わずに TestClient を生成する
    （startup による実 GeoIPResolver.load を回避する）。各テストは必要に応じて
    ``app.state.geoip_resolver`` を上書きし、``AttackEventRepository`` を patch する。

    テスト終了時に dependency_overrides をクリアして他テストへの影響を防ぐ。
    """
    app.dependency_overrides[verify_credentials] = lambda: "testuser"
    app.dependency_overrides[get_db] = _dummy_get_db
    # 既定では未解決 Resolver（各テストで必要に応じ上書き）
    app.state.geoip_resolver = _make_resolver({})

    # lifespan を回避するため with を使わずに生成する
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


# =====================================================================
# プロパティテスト（Hypothesis）
# =====================================================================


# 降順ソート済みの (source_ip, event_count) リストと、対応する解決マップを生成する戦略。
# get_top_ips は repo 側で件数降順・limit 件に絞られる前提のため、モックは降順・
# 最大 limit 件のデータを返すよう組み立てる。
_ip_pool = st.integers(min_value=0, max_value=255).map(lambda n: f"203.0.113.{n}")


@st.composite
def _top_ip_data(draw: st.DrawFn) -> tuple[list[dict[str, object]], MagicMock]:
    """降順ソート済みの Top IP モックデータと Resolver を生成する.

    - 一意な IP を最大 100 件生成する（get_top_ips の最大件数は 100）。
    - 各 IP に件数を割り当て、件数降順に並べる（repo が降順で返す挙動を再現）。
    - 一部 IP は解決済み、一部は未解決になるよう Resolver を構成する。
    """
    ips: list[str] = draw(st.lists(_ip_pool, min_size=0, max_size=100, unique=True))
    # 各 IP に件数を割り当てる
    counts = [draw(st.integers(min_value=0, max_value=10000)) for _ in ips]
    # 件数降順に並べ替える（repo の order_by desc を再現）
    paired = sorted(zip(ips, counts, strict=True), key=lambda t: t[1], reverse=True)

    now = datetime.now(UTC)
    rows: list[dict[str, object]] = [
        {
            "source_ip": ip,
            "event_count": count,
            "first_seen": now,
            "last_seen": now,
        }
        for ip, count in paired
    ]

    # 偶数インデックスの IP のみ解決済みにする（残りは未解決 → geo 各 null）
    ip_to_location: dict[str, GeoLocation] = {}
    for i, (ip, _count) in enumerate(paired):
        if i % 2 == 0:
            ip_to_location[ip] = _resolved_location("JP")
    resolver = _make_resolver(ip_to_location)
    return rows, resolver


# Feature: 4-feat-geoip-ip-location, Property 5: Top IP 応答は各エントリに Geo_Location を
# 持ち、件数降順・最大100件である
@given(data=_top_ip_data())
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_top_ips_have_geo_desc_and_capped(
    client: TestClient, data: tuple[list[dict[str, object]], MagicMock]
) -> None:
    """/geo/top-ips の各エントリは geo を持ち、event_count 降順・最大100件である.

    Validates: Requirements 3.3, 3.7
    """
    rows, resolver = data
    app.state.geoip_resolver = resolver

    # AttackEventRepository をモックし、get_top_ips が降順データを返すようにする
    with patch("honeywatch.api.routes.geo.AttackEventRepository") as repo_cls:
        repo = repo_cls.return_value
        repo.get_top_ips = AsyncMock(return_value=rows)

        response = client.get(f"{_BASE}/top-ips", params={"limit": 100, "period": "24h"})

    assert response.status_code == 200
    entries = response.json()["ips"]

    # 最大 100 件
    assert len(entries) <= 100

    geo_keys = {"country_code", "country_name", "region", "city", "latitude", "longitude"}
    prev_count: int | None = None
    for entry in entries:
        # 各エントリは必ず geo を持ち、geo は所定のキーを持つ
        assert "geo" in entry
        assert set(entry["geo"].keys()) == geo_keys
        # event_count 降順
        count = entry["event_count"]
        if prev_count is not None:
            assert prev_count >= count
        prev_count = count


# start > end となる ISO 8601 日時ペアを生成する戦略。
_dt_strategy = st.datetimes(
    min_value=datetime(2000, 1, 1),
    max_value=datetime(2100, 1, 1),
)


@st.composite
def _start_after_end(draw: st.DrawFn) -> tuple[str, str]:
    """start > end となる (start, end) の ISO 8601 文字列ペアを生成する."""
    a = draw(_dt_strategy)
    b = draw(_dt_strategy)
    # start が end より後になるよう順序付ける（同時刻は除外）
    if a == b:
        b = b.replace(year=b.year - 1) if b.year > 2000 else b.replace(year=b.year + 1)
    start, end = (max(a, b), min(a, b))
    return start.isoformat(), end.isoformat()


# Feature: 4-feat-geoip-ip-location, Property 9: 開始日時が終了日時より後の期間は
# 常にエラーになる
@given(pair=_start_after_end())
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_start_after_end_returns_400(
    client: TestClient, pair: tuple[str, str]
) -> None:
    """start > end の期間は常に 400 を返し、集計（get_ip_counts）を行わない.

    Validates: Requirements 5.7
    """
    start, end = pair
    app.state.geoip_resolver = _make_resolver({})

    with patch("honeywatch.api.routes.geo.AttackEventRepository") as repo_cls:
        repo = repo_cls.return_value
        repo.get_ip_counts = AsyncMock(return_value=[])

        response = client.get(f"{_BASE}/country-summary", params={"start": start, "end": end})

    assert response.status_code == 400
    # 集計は行われない（get_ip_counts が呼ばれない）
    repo.get_ip_counts.assert_not_called()


# =====================================================================
# ユニットテスト（例示）: /geo/ips/{source_ip}
# =====================================================================


def test_ip_geo_resolved_returns_values(client: TestClient) -> None:
    """解決済み IP の geo に値が入る（Requirement 3.1）."""
    app.state.geoip_resolver = _make_resolver({"8.8.8.8": _resolved_location("US")})

    response = client.get(f"{_BASE}/ips/8.8.8.8")

    assert response.status_code == 200
    body = response.json()
    assert body["source_ip"] == "8.8.8.8"
    assert body["geo"]["country_code"] == "US"
    assert body["geo"]["latitude"] == 35.0
    assert body["geo"]["longitude"] == 139.0


def test_ip_geo_unresolved_returns_nulls(client: TestClient) -> None:
    """未解決 IP は geo 各フィールド null・200 を返す（Requirement 3.2）."""
    # マッピングに無い IP → 未解決
    app.state.geoip_resolver = _make_resolver({})

    response = client.get(f"{_BASE}/ips/9.9.9.9")

    assert response.status_code == 200
    geo = response.json()["geo"]
    assert all(geo[key] is None for key in geo)


def test_ip_geo_invalid_ip_returns_400(client: TestClient) -> None:
    """不正な IP 形式は 400 を返す（Requirement 3.5）."""
    response = client.get(f"{_BASE}/ips/not-an-ip")

    assert response.status_code == 400


def test_ip_geo_resolver_unavailable_returns_nulls(client: TestClient) -> None:
    """Resolver 利用不可（常に未解決を返す）でも geo 各 null・200 を返す（Requirement 3.6）.

    未ロードの Resolver 相当として、resolve が常に未解決を返すモックを注入する。
    500 にせず null 応答となることを検証する。
    """
    unavailable = MagicMock()
    unavailable.resolve.side_effect = lambda ip: GeoLocation.unresolved()
    app.state.geoip_resolver = unavailable

    response = client.get(f"{_BASE}/ips/8.8.8.8")

    assert response.status_code == 200
    geo = response.json()["geo"]
    assert all(geo[key] is None for key in geo)


# =====================================================================
# ユニットテスト（例示）: /geo/country-summary
# =====================================================================


def test_country_summary_invalid_start_returns_400(client: TestClient) -> None:
    """start が ISO 8601 でない場合は 400 を返す（Requirement 5.7）."""
    with patch("honeywatch.api.routes.geo.AttackEventRepository") as repo_cls:
        repo = repo_cls.return_value
        repo.get_ip_counts = AsyncMock(return_value=[])

        response = client.get(f"{_BASE}/country-summary", params={"start": "not-a-date"})

    assert response.status_code == 400
    repo.get_ip_counts.assert_not_called()


def test_country_summary_aggregates_and_sorts(client: TestClient) -> None:
    """複数 IP を国別集計し件数降順で返す。未解決は UNKNOWN 区分になる（Requirement 3.4, 5.9）."""
    # 3 IP: US x2件, JP x5件, 未解決 x1件
    ip_counts = [("8.8.8.8", 2), ("9.9.9.9", 5), ("7.7.7.7", 1)]
    resolver = _make_resolver(
        {
            "8.8.8.8": _resolved_location("US"),
            "9.9.9.9": _resolved_location("JP"),
            # 7.7.7.7 はマップに無い → 未解決 → UNKNOWN
        }
    )
    app.state.geoip_resolver = resolver

    with patch("honeywatch.api.routes.geo.AttackEventRepository") as repo_cls:
        repo = repo_cls.return_value
        repo.get_ip_counts = AsyncMock(return_value=ip_counts)

        response = client.get(f"{_BASE}/country-summary")

    assert response.status_code == 200
    countries = response.json()["countries"]
    # 件数降順: JP(5), US(2), UNKNOWN(1)
    assert countries == [
        {"country_code": "JP", "count": 5},
        {"country_code": "US", "count": 2},
        {"country_code": "UNKNOWN", "count": 1},
    ]


def test_country_summary_resolves_past_data(client: TestClient) -> None:
    """過去日時範囲の (IP, 件数) も都度 resolve され国別集計される（Requirement 6.3, 6.4）.

    get_ip_counts が過去期間の集計結果を返す状況を再現し、各 IP に対して
    resolver.resolve が呼ばれることを確認する。
    """
    past_start = "2020-01-01T00:00:00+00:00"
    past_end = "2020-12-31T23:59:59+00:00"
    ip_counts = [("8.8.8.8", 3), ("9.9.9.9", 4)]
    resolver = _make_resolver(
        {
            "8.8.8.8": _resolved_location("US"),
            "9.9.9.9": _resolved_location("JP"),
        }
    )
    app.state.geoip_resolver = resolver

    with patch("honeywatch.api.routes.geo.AttackEventRepository") as repo_cls:
        repo = repo_cls.return_value
        repo.get_ip_counts = AsyncMock(return_value=ip_counts)

        response = client.get(
            f"{_BASE}/country-summary",
            params={"start": past_start, "end": past_end},
        )

    assert response.status_code == 200
    # 過去期間で get_ip_counts が呼ばれている
    repo.get_ip_counts.assert_awaited_once()
    # 各 IP に対して resolve が呼ばれている（都度解決）
    resolved_ips = {call.args[0] for call in resolver.resolve.call_args_list}
    assert resolved_ips == {"8.8.8.8", "9.9.9.9"}

    countries = response.json()["countries"]
    # 件数降順: JP(4), US(3)
    assert countries == [
        {"country_code": "JP", "count": 4},
        {"country_code": "US", "count": 3},
    ]


def test_country_summary_empty_returns_empty_list(client: TestClient) -> None:
    """集計対象 0 件なら countries は空リスト（Requirement 5.8）."""
    with patch("honeywatch.api.routes.geo.AttackEventRepository") as repo_cls:
        repo = repo_cls.return_value
        repo.get_ip_counts = AsyncMock(return_value=[])

        response = client.get(f"{_BASE}/country-summary")

    assert response.status_code == 200
    assert response.json()["countries"] == []


def test_top_ips_unresolved_entries_have_null_geo(client: TestClient) -> None:
    """Top IP の未解決エントリは geo 各フィールド null になる（Requirement 3.3）."""
    now = datetime.now(UTC)
    rows: list[dict[str, object]] = [
        {"source_ip": "8.8.8.8", "event_count": 10, "first_seen": now, "last_seen": now},
        {"source_ip": "7.7.7.7", "event_count": 5, "first_seen": now, "last_seen": now},
    ]
    # 8.8.8.8 のみ解決、7.7.7.7 は未解決
    app.state.geoip_resolver = _make_resolver({"8.8.8.8": _resolved_location("US")})

    with patch("honeywatch.api.routes.geo.AttackEventRepository") as repo_cls:
        repo = repo_cls.return_value
        repo.get_top_ips = AsyncMock(return_value=rows)

        response = client.get(f"{_BASE}/top-ips")

    assert response.status_code == 200
    entries = response.json()["ips"]
    by_ip = {e["source_ip"]: e for e in entries}
    assert by_ip["8.8.8.8"]["geo"]["country_code"] == "US"
    unresolved_geo = by_ip["7.7.7.7"]["geo"]
    assert all(unresolved_geo[key] is None for key in unresolved_geo)
    # first_seen / last_seen は isoformat 文字列で返る
    assert isinstance(by_ip["8.8.8.8"]["first_seen"], str)


# =====================================================================
# ユニットテスト（例示）: /geo/top-ips の period 対応
# spec 5-feat-dashboard-unified-period（Requirement 6.2, 6.3, 9.1）
# =====================================================================


def test_top_ips_all_passes_since_none(client: TestClient) -> None:
    """period=all で get_top_ips に since=None が渡る（Requirement 6.3）."""
    app.state.geoip_resolver = _make_resolver({})

    with patch("honeywatch.api.routes.geo.AttackEventRepository") as repo_cls:
        repo = repo_cls.return_value
        repo.get_top_ips = AsyncMock(return_value=[])

        response = client.get(f"{_BASE}/top-ips", params={"period": "all"})

    assert response.status_code == 200
    repo.get_top_ips.assert_awaited_once()
    await_args = repo.get_top_ips.await_args
    assert await_args is not None
    assert await_args.kwargs["since"] is None


def test_top_ips_1y_returns_200_with_365_days(client: TestClient) -> None:
    """period=1y で 200 を返し since が直近 365 日（Requirement 6.2）."""
    app.state.geoip_resolver = _make_resolver({})

    with patch("honeywatch.api.routes.geo.AttackEventRepository") as repo_cls:
        repo = repo_cls.return_value
        repo.get_top_ips = AsyncMock(return_value=[])

        response = client.get(f"{_BASE}/top-ips", params={"period": "1y"})

    assert response.status_code == 200
    await_args = repo.get_top_ips.await_args
    assert await_args is not None
    kwargs = await_args.kwargs
    assert kwargs["since"] is not None
    assert kwargs["until"] - kwargs["since"] == timedelta(days=365)


def test_top_ips_invalid_period_returns_422(client: TestClient) -> None:
    """不正 period（30d）は 422、集計を行わない（Requirement 9.1）."""
    app.state.geoip_resolver = _make_resolver({})

    with patch("honeywatch.api.routes.geo.AttackEventRepository") as repo_cls:
        repo = repo_cls.return_value
        repo.get_top_ips = AsyncMock(return_value=[])

        response = client.get(f"{_BASE}/top-ips", params={"period": "30d"})

    assert response.status_code == 422
    repo.get_top_ips.assert_not_called()
