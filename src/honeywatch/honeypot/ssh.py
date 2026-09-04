"""SSH Honeypot 実装.

asyncssh を使用して SSH サーバーを模倣する。
すべての認証試行を記録し、常に認証を失敗させる。
"""

import asyncio
import os
import time
from pathlib import Path

import asyncssh

from honeywatch.collector.events import AttackEvent, SSHEventData
from honeywatch.collector.handler import EventQueue
from honeywatch.core.config import get_settings
from honeywatch.core.logging import get_logger
from honeywatch.honeypot.base import BaseHoneypot

logger = get_logger(__name__)


class SSHHoneypotServer(asyncssh.SSHServer):
    """asyncssh 用の SSH サーバーハンドラー.

    接続ごとにインスタンスが生成される。
    認証試行を記録し、常に拒否する。
    """

    def __init__(self, honeypot: "SSHHoneypot") -> None:
        """SSHHoneypotServer を初期化する.

        Args:
            honeypot: 親の SSHHoneypot インスタンス
        """
        self._honeypot = honeypot
        self._attempts = 0
        self._conn_start = time.time()
        self._peer_addr: tuple[str, int] | None = None
        self._client_version = ""
        # 接続オブジェクトを保持する。
        # client_version はバージョン交換完了後でないと取得できないため、
        # 認証段階（validate_password）で取り直す用途で保持しておく。
        self._conn: asyncssh.SSHServerConnection | None = None
        # connection_lost（同期コールバック）から async の emit_event を
        # asyncio.create_task でスケジュールする際、生成した Task への参照を
        # 保持しておかないと Task が途中で GC される可能性がある。
        # ここで強参照を保持し、完了時に done コールバックで除去する。
        self._pending_tasks: set[asyncio.Task[None]] = set()
        # 接続ユーザー名。begin_auth で受け取り保存する。
        # begin_auth が呼ばれない接続（純粋なポートスキャン・バナー取得のみ）では
        # 空文字のまま connection_lost に到達する（Requirement 1.3 / 2.3）。
        self._username: str = ""

    def connection_made(self, conn: asyncssh.SSHServerConnection) -> None:
        """接続が確立されたときに呼ばれる."""
        self._conn = conn
        peername = conn.get_extra_info("peername")
        if peername:
            self._peer_addr = (peername[0], peername[1])
        # SSH クライアントバージョンの取得を試みる。
        # ただし connection_made は TCP 接続直後に呼ばれ、この時点では
        # SSH バージョン交換が未完了のため空になることが多い。
        # 実際の記録値は validate_password 内で取り直す。
        self._client_version = conn.get_extra_info("client_version", "")
        logger.debug(
            "ssh_honeypot.connection_made",
            source_ip=self._peer_addr[0] if self._peer_addr else "unknown",
            client_version=self._client_version,
        )

    def connection_lost(self, exc: Exception | None) -> None:
        """接続が切断されたときに呼ばれる.

        認証試行が 0 回のまま切断された接続（ポートスキャン、バナー取得のみ、
        公開鍵認証のみ、認証方式確認のみ等）は validate_password が呼ばれず、
        従来は debug ログのみで記録されなかった。この観測漏れを埋めるため、
        self._attempts == 0 の場合に限り event_type="ssh_connection" の
        AttackEvent を 1 件発行する。

        二重記録防止: self._attempts >= 1 の接続は既に validate_password 内で
        ssh_login_attempt として記録済みのため、ここでは ssh_connection を
        発行しない。これにより既存の認証試行記録挙動を保存する。
        """
        # 既存の debug ログ出力は維持する（挙動保存）。
        logger.debug(
            "ssh_honeypot.connection_lost",
            source_ip=self._peer_addr[0] if self._peer_addr else "unknown",
            attempts=self._attempts,
        )

        # 認証試行が 1 回以上あった接続は ssh_login_attempt で記録済みのため、
        # ここでは何もしない（二重記録防止）。
        if self._attempts != 0:
            return

        # --- 認証試行なし接続（self._attempts == 0）のイベント構築 ---
        # source_ip / source_port は validate_password の既存フォールバックと
        # 値を揃える（未取得時は "0.0.0.0" / 0）。
        source_ip = self._peer_addr[0] if self._peer_addr else "0.0.0.0"
        source_port = self._peer_addr[1] if self._peer_addr else 0

        # raw_data は案B（dict 直接構築）を採用する。
        # ssh_connection は認証情報を持たない接続イベントであり、SSHEventData の
        # 必須フィールド username/password を空文字で埋めると
        # 「認証情報を持たない接続に空の認証フィールドを付与する」ことになり
        # 意味的に不正確で、機密値を必要以上に保存しない方針にも反する。
        # そのため接続イベント専用のフィールドのみを dict で直接構築する。
        # また、raw_data に username/password を含めないことで、分類器の
        # _is_credential_attack が .get() で None を得て素通りし、既存分類を
        # 壊さない（Preservation の担保）。
        raw_data: dict[str, object] = {
            # 接続段階では SSH バージョン交換が未完了で空になり得るが、
            # 空でもイベント発行は妨げない（Requirement 2.3）。
            "client_version": self._client_version,
            # 接続確立から切断までの経過時間（秒、0 以上）。
            "connection_duration": time.time() - self._conn_start,
            # バグ条件により認証試行は常に 0。
            "auth_attempts": 0,
            # 接続ユーザー名。begin_auth で保存した値。取得できなかった場合は
            # 初期値の空文字となる（Requirement 2.3）。
            # キー名を "username" ではなく "connection_username" とする理由:
            # 分類器 detection/classifier.py の _is_credential_attack は
            # raw_data.get("username") を既知の弱いユーザー名（root/admin 等）と
            # 照合するため、"username" キーで格納すると認証試行のない単なる接続が
            # credential_attack と誤判定される。"connection_username" なら
            # 分類器を変更せず .get("username") が None を返し素通りする。
            "connection_username": self._username,
        }

        event = AttackEvent(
            source_ip=source_ip,
            source_port=source_port,
            destination_port=self._honeypot.port,
            protocol="ssh",
            event_type="ssh_connection",
            raw_data=raw_data,
        )

        # --- 同期 → async ブリッジ ---
        # connection_lost は同期コールバックだが、唯一のイベント投入口
        # emit_event は async。asyncssh のコールバックはイベントループ内から
        # 呼ばれる前提のため、asyncio.create_task でループへスケジュールする。
        # 実行中ループが取得できない場合（RuntimeError）はイベント発行を諦め、
        # warning ログのみとして connection_lost から例外を伝播させない。
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            logger.warning(
                "ssh_honeypot.connection_event_dropped",
                source_ip=source_ip,
                reason="no_running_event_loop",
            )
            return

        # Task を生成し、GC 防止のため強参照を集合に保持する。
        # 完了後は done コールバックで集合から除去する。
        task = asyncio.create_task(self._honeypot.emit_event(event))
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)

        logger.info(
            "ssh_honeypot.connection_event",
            source_ip=source_ip,
            client_version=self._client_version,
        )

    def begin_auth(self, username: str) -> bool:
        """認証を開始する（常に認証を要求する）.

        クライアントが送信した接続ユーザー名を保存する。パスワードを
        送らずに切断された接続でも、標的とされたユーザー名を観測できるようにする。

        Args:
            username: クライアントが送信したユーザー名

        Returns:
            True: 認証が必要（既存挙動を維持）
        """
        # 接続ユーザー名を保存する。asyncssh の内部実装により begin_auth は
        # 同一接続で複数回呼ばれ得るため、単純代入で「最後に受け取った値」を保持する。
        self._username = username
        return True

    def password_auth_supported(self) -> bool:
        """パスワード認証をサポートすることを通知する."""
        return True

    async def validate_password(self, username: str, password: str) -> bool:
        """パスワード認証を検証する（常に失敗させる）.

        認証試行を AttackEvent として記録し、常に False を返す。
        最大試行回数を超えた場合は接続を切断する。

        Args:
            username: 試行されたユーザー名
            password: 試行されたパスワード

        Returns:
            常に False（認証失敗）
        """
        self._attempts += 1

        # client_version を取り直す。
        # connection_made の時点ではバージョン交換前で空になることが多いが、
        # 認証段階まで到達していれば交換は完了しているため確実に取得できる。
        # 取得できなかった場合は既存の値（多くは空文字）を維持する。
        if self._conn is not None:
            self._client_version = self._conn.get_extra_info(
                "client_version", self._client_version
            )

        # パスワードを平文で記録（攻撃パターン分析・辞書攻撃傾向の可視化に使用）
        # リスク認識: DB 漏洩時に攻撃者のパスワードリストとして悪用される可能性がある
        # 判断根拠: セキュリティリサーチにおける分析価値を優先（Cowrie 等の先行事例に準拠）

        # 接続時間を計算
        connection_duration = time.time() - self._conn_start

        # イベントデータ生成
        ssh_data = SSHEventData(
            username=username,
            password=password,
            client_version=self._client_version,
            connection_duration=connection_duration,
            auth_success=False,
        )

        source_ip = self._peer_addr[0] if self._peer_addr else "0.0.0.0"
        source_port = self._peer_addr[1] if self._peer_addr else 0

        event = AttackEvent(
            source_ip=source_ip,
            source_port=source_port,
            destination_port=self._honeypot.port,
            protocol="ssh",
            event_type="ssh_login_attempt",
            raw_data=ssh_data.model_dump(),
        )

        # イベントをキューに投入
        await self._honeypot.emit_event(event)

        logger.info(
            "ssh_honeypot.auth_attempt",
            source_ip=source_ip,
            username=username,
            attempt=self._attempts,
            client_version=self._client_version,
        )

        # 最大試行回数チェック
        settings = get_settings()
        if self._attempts >= settings.honeypot.ssh_max_auth_attempts:
            logger.info(
                "ssh_honeypot.max_attempts_reached",
                source_ip=source_ip,
                attempts=self._attempts,
            )
            # asyncssh は False 返却で切断を処理する

        return False


class SSHHoneypot(BaseHoneypot):
    """SSH Honeypot.

    asyncssh を使って SSH サーバーを模倣する。
    すべての認証試行を記録し、常に失敗させる。
    ホストキーは初回起動時に自動生成し、data/ssh_host_keys/ に永続化する。
    """

    def __init__(self, event_queue: EventQueue) -> None:
        """SSH Honeypot を初期化する.

        Args:
            event_queue: イベント投入先の EventQueue インスタンス
        """
        super().__init__(event_queue)
        self._server: asyncssh.SSHAcceptor | None = None
        settings = get_settings()
        self._host = settings.honeypot.ssh_host
        # コンテナ内でリッスンするポート（非 root のため 2222 等）
        self._port = settings.honeypot.ssh_port
        # イベントに記録する宛先ポート（外部公開ポート、例: 22）
        self._reported_port = settings.honeypot.ssh_reported_port
        self._host_key_dir = settings.honeypot.ssh_host_key_dir
        self._timeout = settings.honeypot.ssh_timeout
        # クライアントに広告するサーバーバナー（OpenSSH 等を偽装）
        self._server_version = settings.honeypot.ssh_server_version

    @property
    def name(self) -> str:
        """Honeypot 名を返す."""
        return "ssh"

    @property
    def port(self) -> int:
        """イベントに記録する宛先ポート（外部公開ポート）を返す."""
        return self._reported_port

    async def start(self) -> None:
        """SSH Honeypot サーバーを起動し、停止されるまで待機する."""
        # ホストキーを取得または生成
        host_keys = self._get_or_create_host_keys()

        # バッファ flush ループを開始
        await self.start_flush_loop()

        # SSH サーバーを起動
        self._server = await asyncssh.create_server(
            lambda: SSHHoneypotServer(self),
            self._host,
            self._port,
            server_host_keys=host_keys,
            login_timeout=self._timeout,
            # 実サーバーに見せかけるためバナーを偽装する
            # （asyncssh が "SSH-2.0-" を自動付与するため接頭辞は不要）
            server_version=self._server_version,
            process_factory=None,
        )

        logger.info(
            "ssh_honeypot.started",
            host=self._host,
            port=self._port,
            server_version=self._server_version,
        )

        # サーバーが閉じるまで待機（stop() が呼ばれるまでブロック）
        await self._server.wait_closed()

    async def stop(self) -> None:
        """SSH Honeypot サーバーを停止する."""
        await self.stop_flush_loop()

        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        logger.info("ssh_honeypot.stopped")

    def _get_or_create_host_keys(self) -> list[str]:
        """SSH ホストキーを取得する。存在しない場合は自動生成する.

        Returns:
            ホストキーファイルパスのリスト
        """
        key_dir = Path(self._host_key_dir)
        key_dir.mkdir(parents=True, exist_ok=True)

        rsa_key_path = key_dir / "ssh_host_rsa_key"
        ed25519_key_path = key_dir / "ssh_host_ed25519_key"

        key_paths: list[str] = []

        # RSA キー
        if not rsa_key_path.exists():
            logger.info("ssh_honeypot.generating_rsa_key")
            rsa_key = asyncssh.generate_private_key("ssh-rsa", key_size=2048)
            rsa_key_path.write_bytes(rsa_key.export_private_key())
            os.chmod(rsa_key_path, 0o600)
        key_paths.append(str(rsa_key_path))

        # Ed25519 キー
        if not ed25519_key_path.exists():
            logger.info("ssh_honeypot.generating_ed25519_key")
            ed25519_key = asyncssh.generate_private_key("ssh-ed25519")
            ed25519_key_path.write_bytes(ed25519_key.export_private_key())
            os.chmod(ed25519_key_path, 0o600)
        key_paths.append(str(ed25519_key_path))

        return key_paths
