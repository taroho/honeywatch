"""Event Worker 実装.

Redis Stream からイベントを消費し、PostgreSQL に永続化するワーカー。
Consumer Group を使用して複数ワーカーのスケールアウトに対応する。
PostgreSQL 接続断時は未 ACK のままイベントを Redis に保持し、復旧後に再処理する。
"""

import asyncio
import signal
import uuid

from honeywatch.collector.events import AttackEvent
from honeywatch.collector.handler import EventQueue
from honeywatch.core.config import get_settings
from honeywatch.core.logging import get_logger, setup_logging
from honeywatch.db.models import AttackEventModel
from honeywatch.db.session import close_db, get_session, init_db
from honeywatch.detection.classifier import (
    ATTACK_SUSPICIOUS,
    SEVERITY_LOW,
    AttackClassifier,
    ClassificationResult,
)
from honeywatch.detection.ipcontext import IPContextStore
from honeywatch.detection.patterns import DetectionRuleLoader

logger = get_logger(__name__)


class EventWorker:
    """Redis Stream → PostgreSQL の永続化ワーカー.

    Consumer Group でイベントを消費し、バリデーション後に DB へ INSERT する。
    DB 接続エラー時はイベントを ACK せず、Redis に保持したまま再試行する。
    """

    def __init__(
        self,
        consumer_name: str = "worker-1",
        batch_size: int = 10,
    ) -> None:
        """ワーカーを初期化する.

        Args:
            consumer_name: Consumer Group 内でのこのワーカーの識別名
            batch_size: 1回の読み取りで取得する最大件数
        """
        self._consumer_name = consumer_name
        self._batch_size = batch_size
        self._running = False
        self._event_queue: EventQueue | None = None
        self._db_retry_delay = 2.0  # DB 接続エラー時のリトライ間隔（秒）
        self._db_max_retries = 10
        # Phase 2: 攻撃分類コンポーネント
        self._classifier: AttackClassifier | None = None
        self._ip_context_store: IPContextStore | None = None
        # Brute Force 判定用の時間窓（Detection Rule から取得）
        self._brute_force_window = 600

    async def start(self) -> None:
        """ワーカーを起動し、イベント消費ループを開始する."""
        settings = get_settings()
        setup_logging(settings.log_level, settings.environment)

        logger.info(
            "worker.starting",
            consumer_name=self._consumer_name,
        )

        # DB 初期化
        init_db()

        # EventQueue 接続
        self._event_queue = EventQueue()
        await self._event_queue.connect()

        # Phase 2: 攻撃分類コンポーネントを初期化
        # Detection Rule を読み込み（不正な YAML なら起動時に例外送出）
        rules = DetectionRuleLoader.load()
        self._classifier = AttackClassifier(rules)
        self._brute_force_window = rules.attack_types.brute_force.time_window
        # IPContext ストア（Redis）に接続
        self._ip_context_store = IPContextStore()
        await self._ip_context_store.connect()

        self._running = True

        logger.info("worker.started", consumer_name=self._consumer_name)

        # イベント消費ループ
        async for entry_id, event in self._event_queue.consume(
            consumer_name=self._consumer_name,
            batch_size=self._batch_size,
        ):
            if not self._running:
                break

            await self._process_event(entry_id, event)

    async def stop(self) -> None:
        """ワーカーを停止する（グレースフルシャットダウン）."""
        logger.info("worker.stopping", consumer_name=self._consumer_name)
        self._running = False

        if self._event_queue is not None:
            await self._event_queue.close()

        if self._ip_context_store is not None:
            await self._ip_context_store.close()

        await close_db()
        logger.info("worker.stopped", consumer_name=self._consumer_name)

    async def _classify_event(self, event: AttackEvent) -> ClassificationResult:
        """イベントを分類する（例外時は suspicious_request にフォールバック）.

        IPContext を Redis から取得・更新し、AttackClassifier で分類する。
        分類処理で例外が発生してもイベントは失われないよう、
        フォールバック結果（suspicious_request / LOW）を返す。

        Args:
            event: 分類対象のイベント

        Returns:
            分類結果（attack_type + severity）
        """
        try:
            assert self._ip_context_store is not None  # noqa: S101
            assert self._classifier is not None  # noqa: S101

            # IPContext を更新して取得（試行回数・接続ポート）
            context = await self._ip_context_store.update_and_get(
                source_ip=event.source_ip,
                destination_port=event.destination_port,
                time_window=self._brute_force_window,
            )

            # 分類実行
            return self._classifier.classify(event, context)

        except Exception as e:
            # 分類失敗時もイベントは保存する（design.md の Error Handling 準拠）
            logger.warning(
                "worker.classification_failed",
                event_id=str(event.id),
                error=str(e),
            )
            return ClassificationResult(
                attack_type=ATTACK_SUSPICIOUS,
                severity=SEVERITY_LOW,
            )

    async def _process_event(self, entry_id: str, event: AttackEvent) -> None:
        """1件のイベントを処理する（DB に保存して ACK）.

        DB 接続エラー時はリトライし、成功するまで ACK しない。
        これにより、DB ダウン時にイベントが失われることを防ぐ。

        Args:
            entry_id: Redis Stream エントリ ID
            event: パース済みの AttackEvent
        """
        # 攻撃分類（DB リトライループの外で1回だけ実行）
        classification = await self._classify_event(event)

        for attempt in range(self._db_max_retries):
            try:
                # AttackEvent → AttackEventModel に変換して保存
                model = AttackEventModel(
                    id=event.id if event.id else uuid.uuid4(),
                    timestamp=event.timestamp,
                    source_ip=event.source_ip,
                    source_port=event.source_port,
                    destination_port=event.destination_port,
                    protocol=event.protocol,
                    event_type=event.event_type,
                    raw_data=event.raw_data,
                    attack_type=classification.attack_type,
                    severity=classification.severity,
                )

                async for session in get_session():
                    session.add(model)
                    await session.commit()

                # DB 保存成功 → ACK
                assert self._event_queue is not None  # noqa: S101
                await self._event_queue.ack(entry_id)

                logger.debug(
                    "worker.event_processed",
                    event_id=str(event.id),
                    entry_id=entry_id,
                    protocol=event.protocol,
                    attack_type=classification.attack_type,
                    severity=classification.severity,
                )
                return

            except Exception as e:
                logger.warning(
                    "worker.db_error",
                    attempt=attempt + 1,
                    error=str(e),
                    event_id=str(event.id),
                )
                if attempt < self._db_max_retries - 1:
                    await asyncio.sleep(self._db_retry_delay * (attempt + 1))
                else:
                    # 最大リトライ回数を超えた場合、ACK せずに次のイベントに進む
                    # イベントは Redis 内に未 ACK として残り、再起動時に再処理される
                    logger.error(
                        "worker.event_failed",
                        event_id=str(event.id),
                        entry_id=entry_id,
                        error=str(e),
                    )


async def run_worker(consumer_name: str = "worker-1") -> None:
    """ワーカーのメインエントリーポイント.

    シグナルハンドリングを設定し、ワーカーを起動する。
    SIGTERM / SIGINT でグレースフルシャットダウンする。

    Args:
        consumer_name: Consumer Group 内でのこのワーカーの識別名
    """
    worker = EventWorker(consumer_name=consumer_name)

    # シグナルハンドラー設定
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("worker.signal_received")
        shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

    # ワーカー起動（バックグラウンドタスク）
    worker_task = asyncio.create_task(worker.start())

    # シャットダウンシグナル、または Worker タスクの終了（＝異常終了）を待つ。
    # 以前は shutdown_event のみを待っていたため、消費ループが例外で終了しても
    # 誰も worker_task を await せず、例外が握り潰されてプロセスが無言のまま
    # 停止する不具合があった。ここで両方を待つことで異常終了を検知する。
    shutdown_wait = asyncio.create_task(shutdown_event.wait())
    done, _pending = await asyncio.wait(
        {worker_task, shutdown_wait},
        return_when=asyncio.FIRST_COMPLETED,
    )

    # Worker タスクが先に終了した場合は異常終了。例外を取り出してログに残し、
    # 例外を送出することで（restart: unless-stopped 下で）プロセスを再起動させる。
    if worker_task in done:
        shutdown_wait.cancel()
        try:
            await worker_task
        except Exception:
            logger.exception("worker.crashed", consumer_name=consumer_name)
            await worker.stop()
            raise
        # 例外なく終了した場合もシャットダウン扱いにする
        await worker.stop()
        return

    # シャットダウンシグナルを受信した場合はグレースフルシャットダウン
    await worker.stop()
    worker_task.cancel()

    try:
        await worker_task
    except asyncio.CancelledError:
        pass
