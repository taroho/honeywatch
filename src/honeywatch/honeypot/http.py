"""HTTP Honeypot 実装.

aiohttp を使用して HTTP サーバーを模倣する。
一般的な Web サーバー（Apache）を装い、すべてのリクエストを記録する。
"""

import asyncio

from aiohttp import web

from honeywatch.collector.events import AttackEvent, HTTPEventData
from honeywatch.collector.handler import EventQueue
from honeywatch.core.config import get_settings
from honeywatch.core.logging import get_logger
from honeywatch.honeypot.base import BaseHoneypot

logger = get_logger(__name__)

# レスポンスヘッダー: 一般的な Apache サーバーを偽装
FAKE_SERVER_HEADERS = {
    "Server": "Apache/2.4.41 (Ubuntu)",
    "X-Powered-By": "PHP/7.4.3",
}

# パス別レスポンス HTML テンプレート
HTML_INDEX = """<!DOCTYPE html>
<html>
<head><title>Welcome</title></head>
<body>
<h1>It works!</h1>
<p>This is the default web page for this server.</p>
</body>
</html>"""

HTML_LOGIN = """<!DOCTYPE html>
<html>
<head><title>Login</title></head>
<body>
<h1>Authorization Required</h1>
<form method="POST" action="/login">
    <label>Username: <input type="text" name="user"></label><br>
    <label>Password: <input type="password" name="pass"></label><br>
    <input type="submit" value="Login">
</form>
</body>
</html>"""

HTML_404 = """<!DOCTYPE html>
<html>
<head><title>404 Not Found</title></head>
<body>
<h1>Not Found</h1>
<p>The requested URL was not found on this server.</p>
<hr>
<address>Apache/2.4.41 (Ubuntu) Server</address>
</body>
</html>"""

ROBOTS_TXT = """User-agent: *
Disallow: /admin/
Disallow: /api/
Disallow: /private/
"""

# 管理系パス（401 を返す対象）
ADMIN_PATHS = {"/admin", "/wp-admin", "/login", "/administrator", "/wp-login.php"}


class HTTPHoneypot(BaseHoneypot):
    """HTTP Honeypot.

    aiohttp を使って HTTP サーバーを模倣する。
    一般的な Web サーバーのレスポンスを返しつつ、全リクエストを記録する。
    """

    def __init__(self, event_queue: EventQueue) -> None:
        """HTTP Honeypot を初期化する.

        Args:
            event_queue: イベント投入先の EventQueue インスタンス
        """
        super().__init__(event_queue)
        settings = get_settings()
        self._host = settings.honeypot.http_host
        self._port = settings.honeypot.http_port
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    @property
    def name(self) -> str:
        """Honeypot 名を返す."""
        return "http"

    @property
    def port(self) -> int:
        """リッスンポートを返す."""
        return self._port

    async def start(self) -> None:
        """HTTP Honeypot サーバーを起動し、停止されるまで待機する."""
        # バッファ flush ループを開始
        await self.start_flush_loop()

        # aiohttp アプリケーション作成
        self._app = web.Application()
        self._app.router.add_route("*", "/{path:.*}", self._handle_request)

        # サーバー起動
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._host, self._port)
        await self._site.start()

        logger.info(
            "http_honeypot.started",
            host=self._host,
            port=self._port,
        )

        # 停止されるまで無限待機（stop() で CancelledError が発生する）
        try:
            await asyncio.get_event_loop().create_future()
        except asyncio.CancelledError:
            pass

    async def stop(self) -> None:
        """HTTP Honeypot サーバーを停止する."""
        await self.stop_flush_loop()

        if self._site is not None:
            await self._site.stop()
        if self._runner is not None:
            await self._runner.cleanup()

        logger.info("http_honeypot.stopped")

    async def _handle_request(self, request: web.Request) -> web.Response:
        """全リクエストを処理し、イベントを記録してレスポンスを返す.

        Args:
            request: 受信した HTTP リクエスト

        Returns:
            パスに応じた HTTP レスポンス
        """
        # リクエスト情報を収集
        source_ip = request.remote or "0.0.0.0"
        # aiohttp では remote にポート情報が含まれない場合がある
        peername = request.transport.get_extra_info("peername") if request.transport else None
        source_port = peername[1] if peername else 0

        # リクエストボディの先頭 1024 バイトを取得
        body_preview: str | None = None
        try:
            body_bytes = await request.read()
            if body_bytes:
                body_preview = body_bytes[:1024].decode("utf-8", errors="replace")
        except Exception:
            pass

        # ヘッダーを辞書に変換
        headers = {k: v for k, v in request.headers.items()}
        user_agent = request.headers.get("User-Agent", "")

        # レスポンスを決定
        response_status, response_body, content_type = self._determine_response(
            request.method, request.path
        )

        # イベントデータ生成
        http_data = HTTPEventData(
            method=request.method,
            path=request.path,
            headers=headers,
            user_agent=user_agent,
            body_preview=body_preview,
            status_code=response_status,
        )

        event = AttackEvent(
            source_ip=source_ip,
            source_port=source_port,
            destination_port=self._port,
            protocol="http",
            event_type="http_request",
            raw_data=http_data.model_dump(),
        )

        # イベントをキューに投入
        await self.emit_event(event)

        logger.info(
            "http_honeypot.request",
            source_ip=source_ip,
            method=request.method,
            path=request.path,
            user_agent=user_agent[:100],
            status=response_status,
        )

        # レスポンスを返す
        return web.Response(
            status=response_status,
            text=response_body,
            content_type=content_type,
            headers=FAKE_SERVER_HEADERS,
        )

    def _determine_response(
        self, method: str, path: str
    ) -> tuple[int, str, str]:
        """パスに応じたレスポンスを決定する.

        Args:
            method: HTTP メソッド
            path: リクエストパス

        Returns:
            (ステータスコード, レスポンスボディ, Content-Type) のタプル
        """
        # ルートパス
        if path == "/" or path == "":
            return 200, HTML_INDEX, "text/html"

        # robots.txt
        if path == "/robots.txt":
            return 200, ROBOTS_TXT, "text/plain"

        # 管理系パス（ログインフォームを返す）
        path_lower = path.rstrip("/").lower()
        if path_lower in ADMIN_PATHS:
            return 401, HTML_LOGIN, "text/html"

        # API パス（JSON エラーを返す）
        if path.startswith("/api"):
            return 403, '{"error": "Forbidden", "message": "Access denied"}', "application/json"

        # その他（404）
        return 404, HTML_404, "text/html"
