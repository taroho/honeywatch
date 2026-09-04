"""攻撃分析 API エンドポイント（api/routes/analysis.py）の period 対応ユニットテスト.

spec `5-feat-dashboard-unified-period` の design.md「Testing Strategy」に沿って、
attack-types / severity-summary / risk-ranking の period 対応を例示で検証する:

    - 1y / all: 200 を返し、all で since=None が repo に渡る
    - 不正 period: 422（集計を行わない）

Property 2（全ルート共有）は test_period.py で網羅するため、本ファイルは
analysis 固有の例示（1y/all・不正 period）に留める。

テスト方針は test_geo.py / test_period.py と同一（dependency_overrides +
AttackEventRepository の patch、lifespan 回避のため TestClient を with なしで生成）。
"""

from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from honeywatch.api.deps import get_db, verify_credentials
from honeywatch.api.main import app

_BASE = "/api/v1/analysis"
_REPO_PATH = "honeywatch.api.routes.analysis.AttackEventRepository"


async def _dummy_get_db() -> Any:
    """get_db を差し替えるダミー依存性."""
    yield None


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


# 各エンドポイントの (URL, repo メソッド名, 戻り値)。
# attack-types → count_by_attack_type(dict), severity-summary → count_by_severity(dict),
# risk-ranking → get_ip_aggregates_for_ranking(list)
_ANALYSIS_ENDPOINTS: list[tuple[str, str, object]] = [
    ("/attack-types", "count_by_attack_type", {}),
    ("/severity-summary", "count_by_severity", {}),
    ("/risk-ranking", "get_ip_aggregates_for_ranking", []),
]


@pytest.mark.parametrize(("path", "method_name", "return_value"), _ANALYSIS_ENDPOINTS)
def test_analysis_all_passes_since_none(
    client: TestClient, path: str, method_name: str, return_value: object
) -> None:
    """period=all で 200 を返し since=None が repo に渡る（Requirement 7.5）."""
    with patch(_REPO_PATH) as repo_cls:
        repo = repo_cls.return_value
        method_mock = AsyncMock(return_value=return_value)
        setattr(repo, method_name, method_mock)
        response = client.get(f"{_BASE}{path}", params={"period": "all"})

    assert response.status_code == 200
    method_mock.assert_awaited_once()
    await_args = method_mock.await_args
    assert await_args is not None
    assert await_args.kwargs["since"] is None


@pytest.mark.parametrize(("path", "method_name", "return_value"), _ANALYSIS_ENDPOINTS)
def test_analysis_1y_returns_200_with_365_days(
    client: TestClient, path: str, method_name: str, return_value: object
) -> None:
    """period=1y で 200 を返し since が直近 365 日（Requirement 7.4）."""
    with patch(_REPO_PATH) as repo_cls:
        repo = repo_cls.return_value
        method_mock = AsyncMock(return_value=return_value)
        setattr(repo, method_name, method_mock)
        response = client.get(f"{_BASE}{path}", params={"period": "1y"})

    assert response.status_code == 200
    await_args = method_mock.await_args
    assert await_args is not None
    kwargs = await_args.kwargs
    assert kwargs["since"] is not None
    assert kwargs["until"] - kwargs["since"] == timedelta(days=365)


@pytest.mark.parametrize(("path", "method_name", "return_value"), _ANALYSIS_ENDPOINTS)
def test_analysis_invalid_period_returns_422(
    client: TestClient, path: str, method_name: str, return_value: object
) -> None:
    """不正 period（30d）は 422、集計を行わない（Requirement 9.1）."""
    with patch(_REPO_PATH) as repo_cls:
        repo = repo_cls.return_value
        method_mock = AsyncMock(return_value=return_value)
        setattr(repo, method_name, method_mock)
        response = client.get(f"{_BASE}{path}", params={"period": "30d"})

    assert response.status_code == 422
    method_mock.assert_not_awaited()


def test_risk_ranking_limit_preserved(client: TestClient) -> None:
    """risk-ranking の limit 範囲（1〜100）は維持され、範囲外は 422（Requirement 9.3）."""
    with patch(_REPO_PATH) as repo_cls:
        repo = repo_cls.return_value
        repo.get_ip_aggregates_for_ranking = AsyncMock(return_value=[])
        # 範囲外 limit は 422
        response = client.get(
            f"{_BASE}/risk-ranking", params={"period": "24h", "limit": "0"}
        )
    assert response.status_code == 422
