"""バッチ再分類（backfill）.

Phase 1 で収集済みの未分類イベント（attack_type IS NULL）を
遡って分類する。`python -m honeywatch.detection.backfill` で実行する。

時系列順にイベントを処理し、送信元 IP ごとの試行回数・接続ポートを
メモリ上で再構築しながら分類する（Redis に依存しない）。
"""

import asyncio
from collections import defaultdict

from sqlalchemy import select, update

from honeywatch.collector.events import AttackEvent
from honeywatch.core.config import get_settings
from honeywatch.core.logging import get_logger, setup_logging
from honeywatch.db.models import AttackEventModel
from honeywatch.db.session import close_db, get_session, init_db
from honeywatch.detection.classifier import AttackClassifier, IPContext
from honeywatch.detection.patterns import DetectionRuleLoader

logger = get_logger(__name__)

# 1回のバッチで処理する件数
BATCH_SIZE = 500


class _IPContextBuilder:
    """バックフィル用のメモリ内 IPContext ビルダー.

    Redis を使わず、時系列順に処理する前提で送信元 IP ごとの
    累積試行回数・接続ポート集合をメモリ上で管理する。

    注意: 本番の IPContextStore は時間窓（TTL）で古い試行を除外するが、
    バックフィルでは過去データ全体を対象とするため、累積カウントで近似する。
    """

    def __init__(self) -> None:
        self._attempts: dict[str, int] = defaultdict(int)
        self._ports: dict[str, set[int]] = defaultdict(set)

    def update_and_get(self, source_ip: str, destination_port: int) -> IPContext:
        """イベントを記録し、更新後の IPContext を返す."""
        self._attempts[source_ip] += 1
        self._ports[source_ip].add(destination_port)
        return IPContext(
            recent_attempts=self._attempts[source_ip],
            distinct_ports=set(self._ports[source_ip]),
        )


async def backfill() -> None:
    """未分類イベントを遡って分類する."""
    settings = get_settings()
    setup_logging(settings.log_level, settings.environment)

    logger.info("backfill.starting")

    init_db()

    # 分類器を初期化
    rules = DetectionRuleLoader.load()
    classifier = AttackClassifier(rules)

    context_builder = _IPContextBuilder()
    total_processed = 0

    try:
        async for session in get_session():
            # 未分類イベントを時系列順に全件取得
            # （IPContext を正しく再構築するため timestamp 昇順で処理する）
            result = await session.execute(
                select(AttackEventModel)
                .where(AttackEventModel.attack_type.is_(None))
                .order_by(AttackEventModel.timestamp.asc())
            )
            events = list(result.scalars().all())

            if not events:
                logger.info("backfill.no_unclassified_events")
                return

            logger.info("backfill.found_events", count=len(events))

            for model in events:
                # DB モデル → AttackEvent に変換して分類
                event = AttackEvent(
                    id=model.id,
                    timestamp=model.timestamp,
                    source_ip=model.source_ip,
                    source_port=model.source_port,
                    destination_port=model.destination_port,
                    protocol=model.protocol,
                    event_type=model.event_type,
                    raw_data=model.raw_data,
                )

                context = context_builder.update_and_get(
                    source_ip=model.source_ip,
                    destination_port=model.destination_port,
                )
                classification = classifier.classify(event, context)

                # 分類結果を UPDATE
                await session.execute(
                    update(AttackEventModel)
                    .where(AttackEventModel.id == model.id)
                    .values(
                        attack_type=classification.attack_type,
                        severity=classification.severity,
                    )
                )

                total_processed += 1
                if total_processed % BATCH_SIZE == 0:
                    await session.commit()
                    logger.info("backfill.progress", processed=total_processed)

            await session.commit()

        logger.info("backfill.completed", total_processed=total_processed)

    finally:
        await close_db()


def main() -> None:
    """バックフィルのエントリーポイント."""
    asyncio.run(backfill())


if __name__ == "__main__":
    main()
