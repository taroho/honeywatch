"""テスト共通フィクスチャ."""

import pytest

from honeywatch.core.config import Settings


@pytest.fixture
def settings() -> Settings:
    """テスト用の設定インスタンスを提供する."""
    return Settings(
        environment="testing",
        log_level="DEBUG",
    )
