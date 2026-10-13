"""HTTP Honeypot 実装.

aiohttp を使用して HTTP サーバーを模倣する。
一般的な Web サーバー（Apache）を装い、すべてのリクエストを記録する。
"""

import asyncio
from dataclasses import dataclass
from urllib.parse import parse_qs

from aiohttp import web

from honeywatch.collector.events import AttackEvent, HTTPEventData
from honeywatch.collector.handler import EventQueue
from honeywatch.core.config import get_max_credential_length, get_settings
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

# email / password のみを持つ簡易ログインフォーム（要件 1.1〜1.3）。
# /login 専用ハンドラ（_handle_login）が GET で 200、POST で 401 とともに返す。
# 入力名は email / password の 2 つのみ、単一の form を POST /login へ送信する。
HTML_LOGIN_EMAIL = """<!DOCTYPE html>
<html>
<head><title>Login</title></head>
<body>
<h1>Authorization Required</h1>
<form method="POST" action="/login">
    <label>Email: <input type="email" name="email"></label><br>
    <label>Password: <input type="password" name="password"></label><br>
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

# 管理系パス（401 を返す対象）。
# `/login` は email/password 専用フォームを扱う `_handle_login` に委譲するため、
# ここには含めない（他の管理系パスの 401 挙動は従来どおり維持する）。
ADMIN_PATHS = {"/admin", "/wp-admin", "/administrator", "/wp-login.php"}

# ログインエンドポイントのパス（正規化後に比較する基準値）
LOGIN_PATH = "/login"

# リクエストボディの上限サイズ（1 MB）。これを超える GET/POST は 413 で拒否し、
# 超過分のボディを永続化しない（要件 1.6）。
MAX_BODY_SIZE = 1_048_576

# ログインエンドポイントで許可する HTTP メソッド（要件 1.7）。
# これ以外のメソッドは 405 を返す。
LOGIN_ALLOWED_METHODS = {"GET", "POST"}


@dataclass
class CredentialSubmission:
    """ログインフォームから抽出した認証情報（Honeypot 内部の中間表現）.

    email / password は常に str であり、フィールドが欠落・空・form 解析失敗の
    いずれの場合も空文字列（長さ 0）となる（要件 2.2, 2.3, 2.5）。各値は
    Max_Credential_Length 以下に切り詰め済み（要件 2.4）。parsed は form 形式
    として解析に成功したか（要件 2.5 の判定用）を表す。

    Attributes:
        email: 抽出した email（切り詰め後、平文）。欠落・空・解析失敗時は空文字列。
        password: 抽出した password（切り詰め後、平文の原文）。欠落・空・解析失敗時は空文字列。
        parsed: form 形式としてボディを解析できたか。
    """

    email: str
    password: str
    parsed: bool


def _truncate(value: str, limit: int) -> str:
    """文字列を先頭 limit 文字に切り詰める（コードポイント単位）.

    要件は「文字数」基準のため、バイト単位ではなく Python の str スライス
    （コードポイント単位）で切り詰める（要件 2.4, 5.5）。

    Args:
        value: 切り詰め対象の文字列。
        limit: 保持する先頭の文字数（Max_Credential_Length）。

    Returns:
        先頭 limit 文字へ切り詰めた文字列（長さは limit 以下）。
    """
    return value[:limit]


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
        # コンテナ内でリッスンするポート
        self._port = settings.honeypot.http_port
        # イベントに記録する宛先ポート（外部公開ポート）
        self._reported_port = settings.honeypot.http_reported_port
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
        # /login は専用ハンドラへ委譲する（要件 1）。
        # path を正規化（末尾スラッシュ除去・小文字化）して判定する。
        # _determine_response 内の ADMIN_PATHS 判定（path.rstrip("/").lower()）と
        # 同じ正規化規則に揃え、/login/ や /LOGIN も同一エンドポイントとして扱う。
        normalized_path = request.path.rstrip("/").lower()
        if normalized_path == LOGIN_PATH:
            return await self._handle_login(request)

        # /login 以外は従来どおりの全リクエスト記録パスを実行する（挙動不変）。
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
        except Exception as e:  # noqa: BLE001 — ボディ取得失敗は記録して継続
            logger.debug("http_honeypot.body_read_failed", error=str(e))

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
            destination_port=self._reported_port,
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

    async def _read_body_limited(self, request: web.Request) -> bytes | None:
        """ボディを MAX_BODY_SIZE まで読み取る（要件 1.6）.

        次の 2 系統で上限を打ち切る。

        1. ``Content-Length`` ヘッダーが MAX_BODY_SIZE を超えると宣言している
           場合、ボディを読まずに即座に ``None`` を返す（宣言された超過分を
           永続化しない）。
        2. 逐次読み取り（``request.content``）の累積サイズが MAX_BODY_SIZE を
           超えた時点で読み取りを打ち切り ``None`` を返す（Content-Length が
           無い / 過少申告のケースに備える）。

        読み取り中に例外が発生した場合は、既存 ``_handle_request`` の方針
        （ボディ取得失敗は記録して継続）を踏襲し、デバッグログを出して空ボディ
        （``b""``）として継続する（要件 2.5 の「記録処理を中断しない」に整合）。

        Args:
            request: 受信した HTTP リクエスト。

        Returns:
            読み取ったボディのバイト列。上限超過時は ``None``、読み取り例外時は
            空ボディ ``b""``。
        """
        # 1) Content-Length による事前判定（宣言値が上限超なら読まずに拒否）。
        content_length = request.content_length
        if content_length is not None and content_length > MAX_BODY_SIZE:
            return None

        # 2) 逐次読み取り。累積サイズが上限を超えた時点で打ち切る。
        chunks: list[bytes] = []
        total = 0
        try:
            async for chunk in request.content.iter_chunked(8192):
                total += len(chunk)
                if total > MAX_BODY_SIZE:
                    # 超過分は保持せず拒否する（要件 1.6）。
                    return None
                chunks.append(chunk)
        except Exception as e:  # noqa: BLE001 — ボディ取得失敗は記録して継続
            logger.debug("http_honeypot.body_read_failed", error=str(e))
            return b""

        return b"".join(chunks)

    async def _handle_login(self, request: web.Request) -> web.Response:
        """``/login`` の GET / POST を処理する（要件 1）.

        - GET: ``HTML_LOGIN_EMAIL`` を 200 + 偽装ヘッダーで返す（要件 1.1〜1.4）。
        - POST: ボディ上限を確認し、超過時は 413（イベント発行しない、要件 1.6）。
          上限内なら認証情報を抽出し、``http_login_attempt`` イベントを 1 件発行
          して 401 を返す（要件 1.5。イベント発行の詳細は後続タスクで拡張）。
        - GET / POST 以外のメソッド: 405（要件 1.7）。

        いずれのレスポンスにも ``FAKE_SERVER_HEADERS`` を付与する（要件 1.4）。
        ログには path / status / method / email 長・エラー種別のみを記録し、
        password 平文および email 値そのものは出力しない（要件 5.6）。

        Args:
            request: 受信した HTTP リクエスト（path は /login に正規化済み）。

        Returns:
            メソッド・ボディサイズに応じた HTTP レスポンス。
        """
        method = request.method

        # GET / POST 以外は許可しない（要件 1.7）。
        if method not in LOGIN_ALLOWED_METHODS:
            logger.info(
                "http_honeypot.login_method_not_allowed",
                method=method,
                path=LOGIN_PATH,
                status=405,
            )
            return web.Response(
                status=405,
                text="Method Not Allowed",
                content_type="text/plain",
                headers=FAKE_SERVER_HEADERS,
            )

        # GET: ログインフォームを 200 で返す（要件 1.1〜1.4）。
        if method == "GET":
            # ログインページへのアクセス自体も観測価値があるため、他パスと同様に
            # http_request イベントとして記録する（email/password は未送信なので None）。
            source_ip = request.remote or "0.0.0.0"
            peername = (
                request.transport.get_extra_info("peername") if request.transport else None
            )
            source_port = peername[1] if peername else 0
            get_event_data = HTTPEventData(
                method=method,
                path=request.path,
                headers={k: v for k, v in request.headers.items()},
                user_agent=request.headers.get("User-Agent", ""),
                body_preview=None,
                status_code=200,
            )
            get_event = AttackEvent(
                source_ip=source_ip,
                source_port=source_port,
                destination_port=self._reported_port,
                protocol="http",
                event_type="http_request",
                raw_data=get_event_data.model_dump(),
            )
            await self.emit_event(get_event)
            logger.info(
                "http_honeypot.login_form",
                method=method,
                path=LOGIN_PATH,
                status=200,
            )
            return web.Response(
                status=200,
                text=HTML_LOGIN_EMAIL,
                content_type="text/html",
                headers=FAKE_SERVER_HEADERS,
            )

        # POST: ボディ上限を確認する（要件 1.6）。
        raw_body = await self._read_body_limited(request)
        if raw_body is None:
            # 上限超過。イベントは発行せず 413 を返す（超過分を永続化しない）。
            logger.info(
                "http_honeypot.login_payload_too_large",
                method=method,
                path=LOGIN_PATH,
                status=413,
            )
            return web.Response(
                status=413,
                text="Payload Too Large",
                content_type="text/plain",
                headers=FAKE_SERVER_HEADERS,
            )

        # 認証情報を抽出する（切り詰め・form 解析失敗ハンドリングは _extract_credentials
        # 内で完結し、例外は送出しない）。POST の正常系イベント発行（HTTPEventData の
        # email/password 設定・AttackEvent 生成・emit_event）はこの経路で行う。
        submission = self._extract_credentials(raw_body)

        # 「実際に存在し非空だったか」を空文字判定で確認し、存在かつ非空のときのみ
        # raw_data に str を設定、それ以外は None とする（要件 2.2/2.3 と 3.4 の整合）。
        email_value = submission.email if submission.email else None
        password_value = submission.password if submission.password else None

        source_ip = request.remote or "0.0.0.0"
        peername = request.transport.get_extra_info("peername") if request.transport else None
        source_port = peername[1] if peername else 0

        http_data = HTTPEventData(
            method=method,
            path=request.path,
            headers={k: v for k, v in request.headers.items()},
            user_agent=request.headers.get("User-Agent", ""),
            body_preview=None,
            status_code=401,
            email=email_value,
            password=password_value,
        )

        event = AttackEvent(
            source_ip=source_ip,
            source_port=source_port,
            destination_port=self._reported_port,
            protocol="http",
            event_type="http_login_attempt",
            raw_data=http_data.model_dump(),
        )

        # 発行はここで 1 回だけ行う（二重発行を避けるため _handle_request の
        # 記録パスは通さない）。
        await self.emit_event(event)

        # ログは password 平文・email 値そのものを出さず、email 長のみを記録する。
        logger.info(
            "http_honeypot.login_attempt",
            method=method,
            path=LOGIN_PATH,
            status=401,
            email_length=len(submission.email),
            parsed=submission.parsed,
        )

        # 認証失敗を模す 401 を返す（要件 1.5）。
        return web.Response(
            status=401,
            text=HTML_LOGIN_EMAIL,
            content_type="text/html",
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

    def _extract_credentials(self, raw_body: bytes) -> CredentialSubmission:
        """form ボディから email / password を抽出・切り詰めする（要件 2）.

        ``application/x-www-form-urlencoded`` 形式のボディを標準ライブラリの
        ``urllib.parse.parse_qs`` で解析する。解析可能なら ``email`` / ``password``
        フィールドの値を取り出し、Max_Credential_Length で切り詰める（要件 2.1,
        2.4）。フィールドが存在しない、または値が空のときは空文字列とする
        （要件 2.2, 2.3）。ボディが form 形式として解析できない（UTF-8 として
        デコードできない等）場合は email / password をいずれも空文字列、
        ``parsed=False`` とし、例外を送出せず呼び出し側の処理継続を可能にする
        （要件 2.5）。

        切り詰め後の email / password の「実際に存在し非空だったか」は、
        空文字列か否かで判定できる（後段のイベント生成で raw_data の null 変換に
        用いる）。

        Args:
            raw_body: リクエストボディのバイト列。

        Returns:
            抽出・切り詰め済みの CredentialSubmission。
        """
        limit = get_max_credential_length()

        # ボディを UTF-8 としてデコードする。デコードできない（ランダムバイト等の
        # 非 form ボディ）場合は form 形式として解析不能とみなす（要件 2.5）。
        try:
            decoded = raw_body.decode("utf-8")
        except UnicodeDecodeError:
            return CredentialSubmission(email="", password="", parsed=False)

        # parse_qs は非 form 文字列でも例外を送出しないため、デコードに成功した
        # 時点で form 解析成功とみなす。該当フィールドが無ければ空文字列になる。
        parsed_qs = parse_qs(decoded, keep_blank_values=True)

        # parse_qs は値をリストで返すため先頭要素を採用する。欠落時は空文字列。
        email_values = parsed_qs.get("email", [])
        password_values = parsed_qs.get("password", [])
        email = email_values[0] if email_values else ""
        password = password_values[0] if password_values else ""

        return CredentialSubmission(
            email=_truncate(email, limit),
            password=_truncate(password, limit),
            parsed=True,
        )
