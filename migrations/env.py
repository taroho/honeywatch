"""Alembic マイグレーション環境設定.

非同期 SQLAlchemy エンジンを使用してマイグレーションを実行する。
アプリケーションの Settings から接続 URL を取得する。
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from honeywatch.core.config import get_settings
from honeywatch.db.models import Base

# Alembic Config オブジェクト
config = context.config

# ログ設定
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# メタデータ（autogenerate 用）
target_metadata = Base.metadata

# アプリケーション設定から DB URL を取得して設定に注入
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.db.async_url)


def run_migrations_offline() -> None:
    """オフラインモードでマイグレーションを実行する.

    DB 接続なしで SQL を生成する。
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """マイグレーションを実行する（同期コンテキスト内）."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """非同期エンジンを使用してマイグレーションを実行する."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """オンラインモードでマイグレーションを実行する.

    非同期エンジンを使用して DB に接続し、マイグレーションを適用する。
    """
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
