"""ヘルスチェックエンドポイント.

認証不要。システムの各コンポーネントの稼働状態を返す。
"""

import redis.asyncio as aioredis
from fastapi import APIRouter
from sqlalchemy import text

from honeywatch.core.config import get_settings
from honeywatch.db.session import get_session

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, object]:
    """ヘルスチェック: DB / Redis の接続状態を確認する.

    Returns:
        各コンポーネントの稼働状態
    """
    settings = get_settings()
    components: dict[str, str] = {}

    # PostgreSQL チェック
    try:
        async for session in get_session():
            await session.execute(text("SELECT 1"))
            components["database"] = "up"
    except Exception:
        components["database"] = "down"

    # Redis チェック
    try:
        redis_client = aioredis.from_url(settings.redis.url)
        await redis_client.ping()
        await redis_client.close()
        components["redis"] = "up"
    except Exception:
        components["redis"] = "down"

    # 全体ステータス判定
    all_up = all(v == "up" for v in components.values())
    overall_status = "healthy" if all_up else "degraded"

    return {
        "status": overall_status,
        "components": components,
    }
