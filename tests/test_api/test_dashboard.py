"""Dashboard API エンドポイント（api/routes/dashboard.py）のプロパティ/ユニットテスト.

spec `5-feat-dashboard-unified-period` の design.md に沿って以下を検証する:

    - Property 4: 1y / all のタイムラインは時間単位以上の粒度に丸められる
      （`get_timeline` へ渡る `interval_minutes >= 60`）
    - summary の period 反映（period 別の since/until、未指定既定 24h、all の since=None・
      period_start=null）
    - timeline の 1y/all 対応と interval 維持（クランプ対象外）
    - 不正 period（422）

テスト方針は test_geo.py / test_period.py と同一（dependency_overrides + AttackEventRepository
の patch、lifespan 回避のため TestClient を with なしで生成）。
"""

from collections.abc import Iterator, Mapping
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from honeywatch.api.deps import get_db, verify_credentials
from honeywatch.api.main import app
from honeywatch.db.repositories.attack import _MONTH_SENTINEL

_BASE = "/api/v1/dashboard"
_REPO_PATH = "honeywatch.api.routes.dashboard.AttackEventRepository"
_TOLERANCE = timedelta(seconds=5)

_SUMMARY_RETURN = {
    "total": 0,
    "unique_ips": 0,
    "ssh_attempts": 0,
    "http_attacks": 0,
}


async def _dummy_get_db() -> Any:
    """get_db を差し替えるダミー依存性."""
    yield None


def _await_kwargs(mock: AsyncMock) -> Mapping[str, Any]:
    """AsyncMock の await_args.kwargs を取得する（None ガード付き）."""
    await_args = mock.await_args
    assert await_args is not None, "mock was not awaited"
    return await_args.kwargs


@pytest.fixture
def client() -> Iterator[TestClient]:
    """認証無効・ダミー DB を注入した TestClient（lifespan 回避のため with なし）."""
    app.dependency_overrides[verify_credentials] = lambda: "testuser"
    app.dependency_overrides[get_db] = _dummy_get_db
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


# =====================================================================
# Property 4: 1y / all のタイムライン粒度クランプ
# =====================================================================


# Feature: 5-feat-dashboard-unified-period, Property 4: 1y / all のタイムラインは時間単位
# 以上の粒度に丸められる（period in (1y, all) かつ interval 5m/15m/1h のとき、
# get_timeline に渡る interval_minutes は 60 以上）。
@given(
    period=st.sampled_from(["1y", "all"]),
    interval=st.sampled_from(["5m", "15m", "1h"]),
)
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_property_timeline_granularity_clamped_for_long_periods(
    client: TestClient, period: str, interval: str
) -> None:
    """1y / all のタイムラインは interval_minutes>=60 にクランプされる.

    Validates: Requirements 5.5
    """
    with patch(_REPO_PATH) as repo_cls:
        repo = repo_cls.return_value
        repo.get_timeline = AsyncMock(return_value=[])
        response = client.get(
            f"{_BASE}/timeline", params={"period": period, "interval": interval}
        )

    assert response.status_code == 200
    repo.get_timeline.assert_awaited_once()
    kwargs = _await_kwargs(repo.get_timeline)
    assert kwargs["interval_minutes"] >= 60


# =====================================================================
# summary の period 反映（unit / example）
# =====================================================================


def _call_summary(client: TestClient, params: dict[str, str]) -> tuple[Any, AsyncMock]:
    """/dashboard/summary を呼び、(response, get_summary mock) を返す."""
    with patch(_REPO_PATH) as repo_cls:
        repo = repo_cls.return_value
        get_summary = AsyncMock(return_value=_SUMMARY_RETURN)
        repo.get_summary = get_summary
        response = client.get(f"{_BASE}/summary", params=params)
    return response, get_summary


def test_summary_period_1h_and_7d_differ(client: TestClient) -> None:
    """period=1h と period=7d で get_summary に渡る since/until の幅が異なる（Requirement 4.2）."""
    resp1, mock1 = _call_summary(client, {"period": "1h"})
    resp7, mock7 = _call_summary(client, {"period": "7d"})

    assert resp1.status_code == 200
    assert resp7.status_code == 200

    kw1 = _await_kwargs(mock1)
    kw7 = _await_kwargs(mock7)
    assert kw1["until"] - kw1["since"] == timedelta(hours=1)
    assert kw7["until"] - kw7["since"] == timedelta(days=7)


def test_summary_default_is_24h(client: TestClient) -> None:
    """period 未指定時は 24h 相当で集計する（Requirement 4.3, 9.2）."""
    with patch(_REPO_PATH) as repo_cls:
        repo = repo_cls.return_value
        repo.get_summary = AsyncMock(return_value=_SUMMARY_RETURN)
        response = client.get(f"{_BASE}/summary")

    assert response.status_code == 200
    kwargs = _await_kwargs(repo.get_summary)
    assert kwargs["until"] - kwargs["since"] == timedelta(hours=24)


def test_summary_all_since_none_and_period_start_null(client: TestClient) -> None:
    """period=all は since=None を repo に渡し、period_start が null になる（Requirement 3.2）."""
    response, get_summary = _call_summary(client, {"period": "all"})

    assert response.status_code == 200
    kwargs = _await_kwargs(get_summary)
    assert kwargs["since"] is None
    body = response.json()
    assert body["period_start"] is None
    assert body["period_end"] is not None


def test_summary_1y_returns_200_with_365_days(client: TestClient) -> None:
    """period=1y は 200 を返し since が直近 365 日（Requirement 4.2, 7.4）."""
    response, get_summary = _call_summary(client, {"period": "1y"})
    assert response.status_code == 200
    kwargs = _await_kwargs(get_summary)
    assert kwargs["since"] is not None
    assert kwargs["until"] - kwargs["since"] == timedelta(days=365)


def test_summary_invalid_period_xyz_returns_422(client: TestClient) -> None:
    """period=xyz は 422、集計を行わない（Requirement 9.1）."""
    response, get_summary = _call_summary(client, {"period": "xyz"})
    assert response.status_code == 422
    get_summary.assert_not_awaited()


def test_summary_invalid_period_30d_returns_422(client: TestClient) -> None:
    """period=30d は受理集合外のため 422（Requirement 9.1）."""
    response, get_summary = _call_summary(client, {"period": "30d"})
    assert response.status_code == 422
    get_summary.assert_not_awaited()


# =====================================================================
# timeline の 1y/all 対応・interval 維持（unit / example）
# =====================================================================


def test_timeline_all_since_none(client: TestClient) -> None:
    """period=all は since=None を get_timeline に渡す（Requirement 5.3）."""
    with patch(_REPO_PATH) as repo_cls:
        repo = repo_cls.return_value
        repo.get_timeline = AsyncMock(return_value=[])
        response = client.get(f"{_BASE}/timeline", params={"period": "all"})

    assert response.status_code == 200
    assert _await_kwargs(repo.get_timeline)["since"] is None


def test_timeline_interval_5m_preserved_for_24h(client: TestClient) -> None:
    """period=24h&interval=5m はクランプ対象外で interval_minutes=5 が渡る（Requirement 5.4）."""
    with patch(_REPO_PATH) as repo_cls:
        repo = repo_cls.return_value
        repo.get_timeline = AsyncMock(return_value=[])
        response = client.get(
            f"{_BASE}/timeline", params={"period": "24h", "interval": "5m"}
        )

    assert response.status_code == 200
    assert _await_kwargs(repo.get_timeline)["interval_minutes"] == 5


def test_timeline_invalid_period_returns_422(client: TestClient) -> None:
    """timeline の不正 period は 422（Requirement 9.1）."""
    with patch(_REPO_PATH) as repo_cls:
        repo = repo_cls.return_value
        repo.get_timeline = AsyncMock(return_value=[])
        response = client.get(f"{_BASE}/timeline", params={"period": "30d"})

    assert response.status_code == 422
    repo.get_timeline.assert_not_awaited()


# =====================================================================
# spec 5.01-fix-timeline-monthly-bucket:
#   1y / all は月単位（_MONTH_SENTINEL）で集計する。
#   1h/6h/24h/7d は interval に応じた粒度で集計する（後方互換）。
# =====================================================================


# Feature: 5.01-fix-timeline-monthly-bucket, Property 1: 1y / all は月粒度（番兵値）で集計
# される（period in (1y, all) かつ interval 5m/15m/1h のとき、get_timeline に渡る
# interval_minutes は _MONTH_SENTINEL 以上）。
@given(
    period=st.sampled_from(["1y", "all"]),
    interval=st.sampled_from(["5m", "15m", "1h"]),
)
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_property_timeline_monthly_for_long_periods(
    client: TestClient, period: str, interval: str
) -> None:
    """1y / all は interval によらず月粒度（interval_minutes >= _MONTH_SENTINEL）で集計する.

    Validates: Requirements 1.1, 1.2, 1.3
    """
    with patch(_REPO_PATH) as repo_cls:
        repo = repo_cls.return_value
        repo.get_timeline = AsyncMock(return_value=[])
        response = client.get(
            f"{_BASE}/timeline", params={"period": period, "interval": interval}
        )

    assert response.status_code == 200
    repo.get_timeline.assert_awaited_once()
    kwargs = _await_kwargs(repo.get_timeline)
    assert kwargs["interval_minutes"] >= _MONTH_SENTINEL


# Feature: 5.01-fix-timeline-monthly-bucket, Property 2: 1h/6h/24h/7d は interval に応じた
# 粒度で集計される（interval_minutes == {5m:5,15m:15,1h:60}[interval] かつ
# < _MONTH_SENTINEL＝月粒度に丸められない）。
@given(
    period=st.sampled_from(["1h", "6h", "24h", "7d"]),
    interval=st.sampled_from(["5m", "15m", "1h"]),
)
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_property_timeline_short_periods_respect_interval(
    client: TestClient, period: str, interval: str
) -> None:
    """1h/6h/24h/7d は interval を反映し、月粒度に丸められない（後方互換）.

    Validates: Requirements 2.1, 2.2, 5.4
    """
    expected = {"5m": 5, "15m": 15, "1h": 60}[interval]
    with patch(_REPO_PATH) as repo_cls:
        repo = repo_cls.return_value
        repo.get_timeline = AsyncMock(return_value=[])
        response = client.get(
            f"{_BASE}/timeline", params={"period": period, "interval": interval}
        )

    assert response.status_code == 200
    kwargs = _await_kwargs(repo.get_timeline)
    assert kwargs["interval_minutes"] == expected
    assert kwargs["interval_minutes"] < _MONTH_SENTINEL


def test_timeline_1y_uses_month_sentinel(client: TestClient) -> None:
    """period=1y（interval 既定）で interval_minutes が _MONTH_SENTINEL（Requirement 1.1）."""
    with patch(_REPO_PATH) as repo_cls:
        repo = repo_cls.return_value
        repo.get_timeline = AsyncMock(return_value=[])
        response = client.get(f"{_BASE}/timeline", params={"period": "1y"})

    assert response.status_code == 200
    assert _await_kwargs(repo.get_timeline)["interval_minutes"] == _MONTH_SENTINEL


def test_timeline_all_month_sentinel_ignores_interval(client: TestClient) -> None:
    """period=all&interval=5m でも月粒度（interval 非依存、Requirement 1.3）."""
    with patch(_REPO_PATH) as repo_cls:
        repo = repo_cls.return_value
        repo.get_timeline = AsyncMock(return_value=[])
        response = client.get(
            f"{_BASE}/timeline", params={"period": "all", "interval": "5m"}
        )

    assert response.status_code == 200
    assert _await_kwargs(repo.get_timeline)["interval_minutes"] == _MONTH_SENTINEL


def test_timeline_7d_default_interval_is_60(client: TestClient) -> None:
    """period=7d（interval 既定 1h）で interval_minutes=60（Requirement 2.2）."""
    with patch(_REPO_PATH) as repo_cls:
        repo = repo_cls.return_value
        repo.get_timeline = AsyncMock(return_value=[])
        response = client.get(f"{_BASE}/timeline", params={"period": "7d"})

    assert response.status_code == 200
    assert _await_kwargs(repo.get_timeline)["interval_minutes"] == 60
