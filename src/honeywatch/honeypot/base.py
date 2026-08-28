"""Honeypot 基底クラス.

すべての Honeypot が継承する抽象基底クラスを定義する。
共通のイベント発行機能とメモリバッファ（Redis 接続断時のフォールバック）を提供する。
"""

import asyncio
from abc import ABC, abstractmethod
from collections import deque

from honeywatch.collector.events import AttackEvent
from honeywatch.collector.handler import EventQueue
from honeywatch.core.logging import get_logger

logger = get_logger(__name__)

# Redis 接続断時のメモリバッファ最大サイズ
MAX_BUFFER_SIZE = 10000


class BaseHoneypot(ABC):
    """Honeypot の基底クラス.

    すべての Honeypot はこのクラスを継承し、start() / stop() を実装する。
    emit_event() でイベントをキューに投入する。Redis 接続断時は
    メモリ内バッファに一時保持し、再接続後に flush する。
    """

    def __init__(self, event_queue: EventQueue) -> None:
        """基底 Honeypot を初期化する.

        Args:
            event_queue: イベント投入先の EventQueue インスタンス
        """
        self._event_queue = event_queue
        self._buffer: deque[AttackEvent] = deque(maxlen=MAX_BUFFER_SIZE)
        self._flush_task: asyncio.Task[None] | None = None

    @abstractmethod
    async def start(self) -> None:
        """Honeypot サーバーを起動する（サブクラスで実装）."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Honeypot サーバーを停止する（サブクラスで実装）."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Honeypot の名前を返す（ログ用）."""
        ...

    async def emit_event(self, event: AttackEvent) -> None:
        """イベントをキューに投入する.

        Redis 接続に失敗した場合はメモリバッファに一時保持する。
        バッファにイベントがある場合は先にバッファを flush する。

        Args:
            event: 発行する攻撃イベント
        """
        # バッファに溜まっているイベントがあれば先に flush
        if self._buffer:
            await self._flush_buffer()

        try:
            await self._event_queue.publish(event)
        except (ConnectionError, OSError) as e:
            logger.warning(
                "honeypot.buffer_event",
                honeypot=self.name,
                event_id=str(event.id),
                buffer_size=len(self._buffer),
                error=str(e),
            )
            self._buffer.append(event)

    async def _flush_buffer(self) -> None:
        """メモリバッファに溜まったイベントを Redis に flush する.

        1件ずつ publish を試み、失敗したら flush を中断する
        （残りは次回の emit_event 時に再試行される）。
        """
        flushed = 0
        while self._buffer:
            event = self._buffer[0]
            try:
                await self._event_queue.publish(event)
                self._buffer.popleft()
                flushed += 1
            except (ConnectionError, OSError):
                # まだ接続できない → flush を中断
                break

        if flushed > 0:
            logger.info(
                "honeypot.buffer_flushed",
                honeypot=self.name,
                flushed=flushed,
                remaining=len(self._buffer),
            )

    async def start_flush_loop(self) -> None:
        """バックグラウンドでバッファの定期 flush を行うループを起動する."""
        self._flush_task = asyncio.create_task(self._periodic_flush())

    async def stop_flush_loop(self) -> None:
        """バッファ flush ループを停止する."""
        if self._flush_task is not None:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

    async def _periodic_flush(self) -> None:
        """10秒ごとにバッファの flush を試みるバックグラウンドタスク."""
        while True:
            await asyncio.sleep(10)
            if self._buffer:
                await self._flush_buffer()
