"""period 変換の共通ヘルパーおよび period 対応エンドポイントのプロパティ/ユニットテスト.

spec `5-feat-dashboard-unified-period` の design.md「Correctness Properties」のうち、
本ファイルでは以下を検証する:

    - Property 1: period → (since, until) 変換の一貫性（`resolve_period_range` 単体）
    - Property 2: 全 period 対応エンドポイントが同一の period 変換を共有する
    - Property 3: 不正な period はエラー応答（422）となり集計を返さない

テスト方針（design.md「Testing Strategy」/ 既存 test_geo.py に準拠）:
    実 DB には依存させない。FastAPI の ``app.dependency_overrides`` で
    ``verify_credentials`` / ``get_db`` を無効化し、各ルートが import している
    ``AttackEventRepository`` を ``patch`` してモック（AsyncMock）に差し替える。
    geo top-ips のみ Resolver を必要とするため ``app.state.geoip_resolver`` に
    MagicMock を注入する。

    lifespan（startup で実 GeoIPResolver.load が走る）を回避するため、TestClient は
    ``with`` を使わずに生成する（test_geo.py と同一方針）。
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
from honeywatch.api.period import _PERIOD_MAP, resolve_period_range

# 受理される period（PERIOD_PATTERN と一致）
_ACCEPTED_PERIODS = ["1h", "6h", "24h", "7d", "1y", "all"]

# 各 API のベースパス
_BASE = "/api/v1"

# (since, until) の照合で許容する時刻誤差（now を 2 度取るため数秒の差が出る）
_TOLERANCE = timedelta(seconds=5)


# =====================================================================
# Property 1: resolve_period_range 単体
# =====================================================================


# Feature: 5-feat-dashboard-unified-period, Property 1: period → (since, until) 変換の一貫性.
# all→since=None・until≈now、1y→until-since==365日、他→until-since==_PERIOD_MAP[period]、
# いずれも until は now（要求受信時刻）に一致する。
@given(period=st.sampled_from(_ACCEPTED_PERIODS))
@settings(max_examples=100)
def test_property_resolve_period_range_consistency(period: str) -> None:
    """resolve_period_range が period ごとに定義どおりの (since, until) を返す.

    Validates: Requirements 3.1, 3.2, 3.3, 5.2, 5.3, 7.4, 7.5
    """
    before = datetime.now(UTC)
    since, until = resolve_period_range(period)
    after = datetime.now(UTC)

    # until は常に呼び出し時点の now（要求受信時刻）とほぼ一致する
    assert before - _TOLERANCE <= until <= after + _TOLERANCE

    if period == "all":
        # all は下限なし（since=None）
        assert since is None
    elif period == "1y":
        # 1y は直近 365 日
        assert since is not None
        assert until - since == timedelta(days=365)
    else:
        # 他は _PERIOD_MAP の timedelta と一致
        assert since is not None
        assert until - since == _PERIOD_MAP[period]


def test_resolve_period_range_all_returns_none_since() -> None:
    """例示: all は since=None・until≈now を返す（Requirement 3.2）."""
    before = datetime.now(UTC)
    since, until = resolve_period_range("all")
    after = datetime.now(UTC)
    assert since is None
    assert before - _TOLERANCE <= until <= after + _TOLERANCE


def test_resolve_period_range_1y_returns_365_days() -> None:
    """例示: 1y は until-since==365日（Requirement 3.1, 5.2, 7.4）."""
    since, until = resolve_period_range("1y")
    assert since is not None
    assert until - since == timedelta(days=365)


def test_resolve_period_range_24h_returns_24_hours() -> None:
    """例示: 24h は until-since==24時間（Requirement 3.3）."""
    since, until = resolve_period_range("24h")
    assert since is not None
    assert until - since == timedelta(hours=24)


# =====================================================================
# 共通フィクスチャ / ヘルパー（Property 2・3 用）
# =====================================================================


async def _dummy_get_db() -> Any:
    """get_db を差し替えるダミー依存性（Repository を patch するため実体は不要）."""
    yield None


@pytest.fixture
def client() -> Iterator[TestClient]:
    """認証無効・ダミー DB・モック Resolver を注入した TestClient を提供する.

    lifespan を回避するため ``with`` を使わずに生成する（test_geo.py と同一方針）。
    """
    app.dependency_overrides[verify_credentials] = lambda: "testuser"
    app.dependency_overrides[get_db] = _dummy_get_db
    # geo top-ips 用に未解決 Resolver を注入（resolve は常に未解決を返す）
    resolver = MagicMock()
    resolver.resolve.side_effect = lambda ip: GeoLocation.unresolved()
    app.state.geoip_resolver = resolver

    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


# period 対応エンドポイントの定義:
#   (URL, patch 対象モジュールパス, repo メソッド名, 追加パラメータ)
# repo メソッドはいずれも (since=, until=, ...) をキーワードで呼ばれる。
_ENDPOINTS: list[tuple[str, str, str, dict[str, str]]] = [
    (
        f"{_BASE}/dashboard/summary",
        "honeywatch.api.routes.dashboard.AttackEventRepository",
        "get_summary",
        {},
    ),
    (
        f"{_BASE}/dashboard/timeline",
        "honeywatch.api.routes.dashboard.AttackEventRepository",
        "get_timeline",
        {},
    ),
    (
        f"{_BASE}/analysis/attack-types",
        "honeywatch.api.routes.analysis.AttackEventRepository",
        "count_by_attack_type",
        {},
    ),
    (
        f"{_BASE}/analysis/severity-summary",
        "honeywatch.api.routes.analysis.AttackEventRepository",
        "count_by_severity",
        {},
    ),
    (
        f"{_BASE}/analysis/risk-ranking",
        "honeywatch.api.routes.analysis.AttackEventRepository",
        "get_ip_aggregates_for_ranking",
        {},
    ),
    (
        f"{_BASE}/geo/top-ips",
        "honeywatch.api.routes.geo.AttackEventRepository",
        "get_top_ips",
        {},
    ),
]

# 各 repo メソッドがモックで返す既定値（レスポンス組み立てで壊れない形）。
# get_summary は dict、count_by_severity は dict、他はリストを返す。
_METHOD_RETURN: dict[str, object] = {
    "get_summary": {
        "total": 0,
        "unique_ips": 0,
        "ssh_attempts": 0,
        "http_attacks": 0,
    },
    "get_timeline": [],
    "count_by_attack_type": {},
    "count_by_severity": {},
    "get_ip_aggregates_for_ranking": [],
    "get_top_ips": [],
}


def _call_endpoint(
    client: TestClient,
    url: str,
    repo_path: str,
    method_name: str,
    extra_params: dict[str, str],
    period: str,
) -> tuple[int, Any, MagicMock]:
    """指定エンドポイントを period 付きで呼び、(status, json, repo_method_mock) を返す."""
    params: dict[str, str] = {"period": period, **extra_params}
    with patch(repo_path) as repo_cls:
        repo = repo_cls.return_value
        method_mock = AsyncMock(return_value=_METHOD_RETURN[method_name])
        setattr(repo, method_name, method_mock)
        response = client.get(url, params=params)
    body: Any = None
    try:
        body = response.json()
    except ValueError:
        body = None
    return response.status_code, body, method_mock


# =====================================================================
# Property 2: 全 period 対応エンドポイントが同一の period 変換を共有する
# =====================================================================


# Feature: 5-feat-dashboard-unified-period, Property 2: 全 period 対応エンドポイントは
# 同一の period 変換を共有する（各ルートが repo に渡す since/until が
# resolve_period_range(period) と整合。all→since=None、他→until-since≈_PERIOD_MAP[period]）。
@given(period=st.sampled_from(_ACCEPTED_PERIODS))
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_property_all_endpoints_share_period_conversion(
    client: TestClient, period: str
) -> None:
    """summary/timeline/attack-types/severity/risk-ranking/geo top-ips が
    同一 period に対し同じ (since, until) を repo へ渡す.

    Validates: Requirements 2.2, 4.2, 5.1, 6.1, 7.1, 7.2, 7.3
    """
    for url, repo_path, method_name, extra in _ENDPOINTS:
        before = datetime.now(UTC)
        status, _body, method_mock = _call_endpoint(
            client, url, repo_path, method_name, extra, period
        )
        after = datetime.now(UTC)

        assert status == 200, f"{url} returned {status} for period={period}"
        method_mock.assert_awaited_once()
        await_args = method_mock.await_args
        assert await_args is not None
        kwargs = await_args.kwargs
        since = kwargs["since"]
        until = kwargs["until"]

        # until は要求受信時刻（now）とほぼ一致
        assert before - _TOLERANCE <= until <= after + _TOLERANCE

        if period == "all":
            assert since is None, f"{url}: all should pass since=None"
        else:
            assert since is not None
            expected = timedelta(days=365) if period == "1y" else _PERIOD_MAP[period]
            # until - since が期待 timedelta とほぼ一致（数秒許容）
            diff = until - since
            assert abs(diff - expected) <= _TOLERANCE, (
                f"{url}: period={period} diff={diff} expected={expected}"
            )


# =====================================================================
# Property 3: 不正な period はエラー応答（422）となり集計を返さない
# =====================================================================

# 正常レスポンス本体に含まれるキー（これらが含まれないことを確認する）
_RESPONSE_BODY_KEYS = {
    "attacks_today",
    "timeline",
    "attack_types",
    "severity_summary",
    "ranking",
    "ips",
}


# Feature: 5-feat-dashboard-unified-period, Property 3: 不正な period はエラー応答（422）と
# なり集計を返さない（受理集合を除外した文字列で各ルートが 422、正常レスポンス本体を含まない）。
@given(
    period=st.text(min_size=1, max_size=20).filter(
        lambda s: s not in _ACCEPTED_PERIODS
    )
)
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_property_invalid_period_returns_422(client: TestClient, period: str) -> None:
    """受理集合に含まれない period はすべて 422 で拒否され集計を返さない.

    Validates: Requirements 9.1
    """
    for url, repo_path, method_name, extra in _ENDPOINTS:
        params: dict[str, str] = {"period": period, **extra}
        with patch(repo_path) as repo_cls:
            repo = repo_cls.return_value
            method_mock = AsyncMock(return_value=_METHOD_RETURN[method_name])
            setattr(repo, method_name, method_mock)
            response = client.get(url, params=params)

        assert response.status_code == 422, (
            f"{url}: period={period!r} expected 422 got {response.status_code}"
        )
        # 集計は行われない
        method_mock.assert_not_awaited()
        # 正常レスポンス本体キーを含まない
        body = response.json()
        if isinstance(body, dict):
            assert not (_RESPONSE_BODY_KEYS & set(body.keys())), (
                f"{url}: 422 body unexpectedly contains result keys: {body.keys()}"
            )
