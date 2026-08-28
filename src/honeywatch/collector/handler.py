"""イベントキュー（Redis Stream）ハンドラー.

Honeypot からのイベントを Redis Stream に投入し、
Worker が Consumer Group で消費するための機能を提供する。
"""

import asyncio
from collections.abc import AsyncIterator

import redis.asyncio as aioredis

from honeywatch.collector.events import AttackEvent
from honeywatch.core.config import get_settings
from honeywatch.core.logging import get_logger

logger = get_logger(__name__)

# Redis Stream / Consumer Group の定数
STREAM_KEY = "honeywatch:events"
CONSUMER_GROUP = "honeywatch-workers"


class EventQueue:
    """Redis Stream ベースのイベントキュー.

    Honeypot がイベントを publish し、Worker が consume する。
    Redis 接続断時はリトライを行う。
    """

    def __init__(
        self,
        redis_url: str | None = None,
        stream_key: str = STREAM_KEY,
        consumer_group: str = CONSUMER_GROUP,
    ) -> None:
        """EventQueue を初期化する.

        Args:
            redis_url: Redis 接続 URL。None の場合は設定から取得。
            stream_key: Redis Stream のキー名。
            consumer_group: Consumer Group 名。
        """
        if redis_url is None:
            settings = get_settings()
            redis_url = settings.redis.url

        self._redis_url = redis_url
        self._stream_key = stream_key
        self._consumer_group = consumer_group
        self._redis: aioredis.Redis | None = None
        self._max_retries = 5
        self._retry_delay = 1.0  # 秒

    async def connect(self) -> None:
        """Redis に接続する."""
        self._redis = aioredis.from_url(
            self._redis_url,
            decode_responses=True,
        )
        await self._ensure_consumer_group()
        logger.info("event_queue.connected", redis_url=self._redis_url)

    async def close(self) -> None:
        """Redis 接続を閉じる."""
        if self._redis is not None:
            await self._redis.close()
            self._redis = None
            logger.info("event_queue.closed")

    async def _ensure_consumer_group(self) -> None:
        """Consumer Group が存在しない場合に作成する.

        Stream が存在しない場合は mkstream=True で自動作成する。
        """
        assert self._redis is not None  # noqa: S101
        try:
            await self._redis.xgroup_create(
                self._stream_key,
                self._consumer_group,
                id="0",
                mkstream=True,
            )
            logger.info(
                "event_queue.consumer_group_created",
                group=self._consumer_group,
            )
        except aioredis.ResponseError as e:
            # BUSYGROUP: Consumer Group already exists（正常）
            if "BUSYGROUP" in str(e):
                logger.debug(
                    "event_queue.consumer_group_exists",
                    group=self._consumer_group,
                )
            else:
                raise

    async def publish(self, event: AttackEvent) -> str:
        """イベントを Redis Stream に投入する.

        Args:
            event: 投入する攻撃イベント

        Returns:
            Redis Stream エントリ ID

        Raises:
            ConnectionError: Redis 接続に失敗した場合（リトライ後も）
        """
        for attempt in range(self._max_retries):
            try:
                if self._redis is None:
                    await self.connect()
                assert self._redis is not None  # noqa: S101

                entry_id: str = await self._redis.xadd(
                    self._stream_key,
                    {"event_json": event.to_json_str()},
                )
                logger.debug(
                    "event_queue.published",
                    event_id=str(event.id),
                    entry_id=entry_id,
                )
                return entry_id

            except (aioredis.ConnectionError, OSError) as e:
                logger.warning(
                    "event_queue.publish_retry",
                    attempt=attempt + 1,
                    error=str(e),
                )
                self._redis = None
                if attempt < self._max_retries - 1:
                    await asyncio.sleep(self._retry_delay * (attempt + 1))
                else:
                    raise ConnectionError(
                        f"Redis 接続に失敗しました（{self._max_retries}回リトライ後）"
                    ) from e

        # ここには到達しないが、型チェック用
        raise ConnectionError("Redis 接続に失敗しました")  # pragma: no cover

    async def consume(
        self,
        consumer_name: str = "worker-1",
        batch_size: int = 10,
        block_ms: int = 5000,
    ) -> AsyncIterator[tuple[str, AttackEvent]]:
        """Redis Stream からイベントを Consumer Group で消費する.

        XREADGROUP を使用し、未処理のイベントを読み取る。
        処理後に ACK を呼び出すのは呼び出し側の責任。

        Args:
            consumer_name: Consumer 名（Worker インスタンスの識別子）
            batch_size: 1回の読み取りで取得する最大件数
            block_ms: 新しいメッセージを待つ最大ミリ秒数

        Yields:
            (entry_id, AttackEvent) のタプル
        """
        while True:
            try:
                if self._redis is None:
                    await self.connect()
                assert self._redis is not None  # noqa: S101

                # まず未 ACK のペンディングメッセージを処理
                results = await self._redis.xreadgroup(
                    groupname=self._consumer_group,
                    consumername=consumer_name,
                    streams={self._stream_key: ">"},
                    count=batch_size,
                    block=block_ms,
                )

                if not results:
                    continue

                for _stream_name, messages in results:
                    for entry_id, data in messages:
                        try:
                            event = AttackEvent.from_json_str(data["event_json"])
                            yield entry_id, event
                        except Exception as e:
                            # パースエラー: ログに記録して ACK（Dead Letter 扱い）
                            logger.error(
                                "event_queue.parse_error",
                                entry_id=entry_id,
                                error=str(e),
                            )
                            await self.ack(entry_id)

            except (aioredis.ConnectionError, OSError) as e:
                logger.warning(
                    "event_queue.consume_reconnect",
                    error=str(e),
                )
                self._redis = None
                await asyncio.sleep(self._retry_delay)

    async def ack(self, entry_id: str) -> None:
        """メッセージを ACK する（処理完了マーク）.

        Args:
            entry_id: ACK する Redis Stream エントリ ID
        """
        if self._redis is None:
            await self.connect()
        assert self._redis is not None  # noqa: S101

        await self._redis.xack(self._stream_key, self._consumer_group, entry_id)
        logger.debug("event_queue.acked", entry_id=entry_id)
