"""FastAPI アプリケーション.

HoneyWatch REST API のエントリーポイント。
ルーターの登録、ライフサイクルイベント（起動・シャットダウン時の DB 接続管理）を定義する。
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from honeywatch.analysis.geoip import GeoIPResolver
from honeywatch.api.routes import analysis, attacks, dashboard, geo, health
from honeywatch.core.config import get_settings
from honeywatch.core.logging import setup_logging
from honeywatch.db.session import close_db, init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """アプリケーションライフサイクル管理.

    起動時: DB 初期化、ログ設定、GeoIP_Resolver ロード
    シャットダウン時: GeoIP_Resolver クローズ、DB 接続クローズ
    """
    settings = get_settings()
    setup_logging(settings.log_level, settings.environment)
    init_db()
    # GeoIP_Resolver を起動時に1回構築し app.state に保持（シングルトン）。
    # load はフェイルセーフ設計のため .mmdb 不在・破損でも例外を送出しない。
    app.state.geoip_resolver = GeoIPResolver.load(settings.geoip)
    yield
    # シャットダウン処理。GeoIP のクローズで例外が出ても DB クローズを止めないよう
    # try/finally で分離する。
    try:
        app.state.geoip_resolver.close()
    finally:
        await close_db()


app = FastAPI(
    title="HoneyWatch API",
    description="Honeypot-Based Attack Monitoring & Analysis Platform",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 設定（Dashboard からのアクセスを許可）
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ルーター登録
# health は認証不要（プレフィックスなし）
app.include_router(health.router, prefix="/api/v1")
# dashboard, attacks, analysis, geo は認証必須
app.include_router(dashboard.router, prefix="/api/v1")
app.include_router(attacks.router, prefix="/api/v1")
app.include_router(analysis.router, prefix="/api/v1")
app.include_router(geo.router, prefix="/api/v1")
