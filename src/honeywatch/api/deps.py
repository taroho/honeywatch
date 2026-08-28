"""FastAPI 依存性注入モジュール.

DB セッション取得と Basic Auth 認証のための Depends を提供する。
"""

import secrets
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from honeywatch.core.config import get_settings
from honeywatch.db.session import get_session

# Basic Auth スキーマ
security = HTTPBasic()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """DB セッションを取得する依存性.

    Yields:
        AsyncSession: SQLAlchemy 非同期セッション
    """
    async for session in get_session():
        yield session


def verify_credentials(
    credentials: Annotated[HTTPBasicCredentials, Depends(security)],
) -> str:
    """Basic Auth 認証を検証する.

    Args:
        credentials: 受信した Basic Auth 認証情報

    Returns:
        認証済みのユーザー名

    Raises:
        HTTPException: 認証失敗時（401）
    """
    settings = get_settings()

    # タイミング攻撃を防ぐため secrets.compare_digest を使用
    is_user_correct = secrets.compare_digest(
        credentials.username.encode("utf-8"),
        settings.api.auth_user.encode("utf-8"),
    )
    is_password_correct = secrets.compare_digest(
        credentials.password.encode("utf-8"),
        settings.api.auth_password.encode("utf-8"),
    )

    if not (is_user_correct and is_password_correct):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    return credentials.username


# 型エイリアス（ルートで使用）
DbSession = Annotated[AsyncSession, Depends(get_db)]
AuthUser = Annotated[str, Depends(verify_credentials)]
