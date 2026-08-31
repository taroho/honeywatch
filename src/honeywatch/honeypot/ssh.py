"""SSH Honeypot 実装.

asyncssh を使用して SSH サーバーを模倣する。
すべての認証試行を記録し、常に認証を失敗させる。
"""

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

    def connection_made(self, conn: asyncssh.SSHServerConnection) -> None:
        """接続が確立されたときに呼ばれる."""
        peername = conn.get_extra_info("peername")
        if peername:
            self._peer_addr = (peername[0], peername[1])
        # SSH クライアントバージョンを記録
        self._client_version = conn.get_extra_info("client_version", "")
        logger.debug(
            "ssh_honeypot.connection_made",
            source_ip=self._peer_addr[0] if self._peer_addr else "unknown",
            client_version=self._client_version,
        )

    def connection_lost(self, exc: Exception | None) -> None:
        """接続が切断されたときに呼ばれる."""
        logger.debug(
            "ssh_honeypot.connection_lost",
            source_ip=self._peer_addr[0] if self._peer_addr else "unknown",
            attempts=self._attempts,
        )

    def begin_auth(self, username: str) -> bool:
        """認証を開始する（常に認証を要求する）.

        Returns:
            True: 認証が必要
        """
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
        self._port = settings.honeypot.ssh_port
        self._host_key_dir = settings.honeypot.ssh_host_key_dir
        self._timeout = settings.honeypot.ssh_timeout

    @property
    def name(self) -> str:
        """Honeypot 名を返す."""
        return "ssh"

    @property
    def port(self) -> int:
        """リッスンポートを返す."""
        return self._port

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
            process_factory=None,
        )

        logger.info(
            "ssh_honeypot.started",
            host=self._host,
            port=self._port,
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
