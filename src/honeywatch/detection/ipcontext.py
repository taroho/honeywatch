"""IPContext（送信元 IP の文脈情報）管理.

Brute Force / Port Scan の判定に必要な「時間窓内の試行回数」と
「接続した宛先ポートの集合」を Redis で管理する。

- 試行回数: Sorted Set（スコア=タイムスタンプ）で時間窓内の件数をカウント
- 宛先ポート: Set で保持

いずれも TTL を設定し、古いデータは自動的に消える。
Redis 取得失敗時は空の IPContext を返す（degraded 動作）。
"""

import time

import redis.asyncio as aioredis

from honeywatch.core.config import get_settings
from honeywatch.core.logging import get_logger
from honeywatch.detection.classifier import IPContext

logger = get_logger(__name__)

# Redis キーのプレフィックス
ATTEMPTS_KEY_PREFIX = "honeywatch:ipctx:attempts:"
PORTS_KEY_PREFIX = "honeywatch:ipctx:ports:"

# データ保持期間（秒）— 時間窓より十分長く取る
CONTEXT_TTL = 3600


class IPContextStore:
    """送信元 IP の文脈情報を Redis で管理するストア."""

    def __init__(self, redis_url: str | None = None) -> None:
        """IPContextStore を初期化する.

        Args:
            redis_url: Redis 接続 URL。None の場合は設定から取得。
        """
        if redis_url is None:
            settings = get_settings()
            redis_url = settings.redis.url

        self._redis_url = redis_url
        self._redis: aioredis.Redis | None = None

    async def connect(self) -> None:
        """Redis に接続する."""
        self._redis = aioredis.from_url(self._redis_url, decode_responses=True)

    async def close(self) -> None:
        """Redis 接続を閉じる."""
        if self._redis is not None:
            await self._redis.close()
            self._redis = None

    async def update_and_get(
        self,
        source_ip: str,
        destination_port: int,
        time_window: int = 600,
    ) -> IPContext:
        """イベントを記録し、更新後の IPContext を返す.

        時間窓内の試行回数と接続ポート集合を更新して返す。
        Redis 取得失敗時は空の IPContext を返す（分類は継続する）。

        Args:
            source_ip: 送信元 IP
            destination_port: 宛先ポート
            time_window: 試行回数を集計する時間窓（秒）

        Returns:
            更新後の IPContext
        """
        try:
            if self._redis is None:
                await self.connect()
            assert self._redis is not None  # noqa: S101

            now = time.time()
            window_start = now - time_window

            attempts_key = f"{ATTEMPTS_KEY_PREFIX}{source_ip}"
            ports_key = f"{PORTS_KEY_PREFIX}{source_ip}"

            # パイプラインでまとめて実行
            pipe = self._redis.pipeline()
            # 試行を Sorted Set に追加（スコア=現在時刻、メンバー=一意値）
            pipe.zadd(attempts_key, {f"{now}:{destination_port}": now})
            # 時間窓外の古い試行を削除
            pipe.zremrangebyscore(attempts_key, 0, window_start)
            # 時間窓内の試行回数を取得
            pipe.zcard(attempts_key)
            # 接続ポートを Set に追加
            pipe.sadd(ports_key, destination_port)
            # ポート集合を取得
            pipe.smembers(ports_key)
            # TTL 設定
            pipe.expire(attempts_key, CONTEXT_TTL)
            pipe.expire(ports_key, CONTEXT_TTL)

            results = await pipe.execute()

            # results[2] = zcard の結果（試行回数）
            recent_attempts = int(results[2])
            # results[4] = smembers の結果（ポート集合）
            distinct_ports = {int(p) for p in results[4]}

            return IPContext(
                recent_attempts=recent_attempts,
                distinct_ports=distinct_ports,
            )

        except Exception as e:
            # Redis 取得失敗時は degraded 動作（空コンテキストで分類継続）
            logger.warning(
                "ipcontext.degraded",
                source_ip=source_ip,
                error=str(e),
            )
            return IPContext()
