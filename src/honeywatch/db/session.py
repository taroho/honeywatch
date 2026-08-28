"""SQLAlchemy 非同期セッション管理モジュール.

AsyncSession を生成し、リクエストスコープでのトランザクション管理を行う。
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from honeywatch.core.config import get_settings

# グローバルなエンジンとセッションファクトリ
# アプリ起動時に init_db() で初期化される
_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_db(database_url: str | None = None) -> None:
    """データベースエンジンとセッションファクトリを初期化する.

    Args:
        database_url: データベース接続 URL。None の場合は設定から取得。
    """
    global _engine, _session_factory  # noqa: PLW0603

    if database_url is None:
        settings = get_settings()
        database_url = settings.db.async_url

    _engine = create_async_engine(
        database_url,
        echo=False,
        pool_size=20,
        max_overflow=10,
        pool_pre_ping=True,
    )

    _session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """非同期セッションを生成するジェネレータ.

    FastAPI の Depends で使用する。
    トランザクションの commit / rollback は呼び出し側で管理する。

    Yields:
        AsyncSession: SQLAlchemy 非同期セッション
    """
    if _session_factory is None:
        init_db()

    assert _session_factory is not None  # noqa: S101
    async with _session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def close_db() -> None:
    """データベースエンジンを閉じる（シャットダウン時に呼び出す）."""
    global _engine  # noqa: PLW0603
    if _engine is not None:
        await _engine.dispose()
        _engine = None
