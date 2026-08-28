"""Honeypot エントリーポイント.

`python -m honeywatch.honeypot` で全 Honeypot を一括起動する。
シグナルハンドリング（SIGTERM / SIGINT）によるグレースフルシャットダウンを実装。
個別 Honeypot がクラッシュした場合は自動再起動する。
"""

import asyncio
import signal

from honeywatch.collector.handler import EventQueue
from honeywatch.core.config import get_settings
from honeywatch.core.logging import get_logger, setup_logging
from honeywatch.honeypot.base import BaseHoneypot
from honeywatch.honeypot.http import HTTPHoneypot
from honeywatch.honeypot.ssh import SSHHoneypot

logger = get_logger(__name__)

# 再起動間の待機時間（秒）
RESTART_DELAY = 3.0
# 最大連続クラッシュ回数（これを超えると再起動を停止）
MAX_CONSECUTIVE_CRASHES = 5


async def run_honeypot_with_restart(honeypot: BaseHoneypot) -> None:
    """Honeypot を起動し、クラッシュ時に自動再起動する.

    連続クラッシュが MAX_CONSECUTIVE_CRASHES を超えた場合は再起動を停止する。

    Args:
        honeypot: 起動する Honeypot インスタンス
    """
    consecutive_crashes = 0

    while consecutive_crashes < MAX_CONSECUTIVE_CRASHES:
        try:
            logger.info("honeypot.starting", name=honeypot.name)
            await honeypot.start()

            # start() が正常終了した場合（通常は永続ループなので、ここに来たら停止要求）
            break

        except asyncio.CancelledError:
            # キャンセル要求（グレースフルシャットダウン）
            logger.info("honeypot.cancelled", name=honeypot.name)
            break

        except Exception as e:
            consecutive_crashes += 1
            logger.error(
                "honeypot.crashed",
                name=honeypot.name,
                error=str(e),
                consecutive_crashes=consecutive_crashes,
            )

            if consecutive_crashes >= MAX_CONSECUTIVE_CRASHES:
                logger.error(
                    "honeypot.max_crashes_reached",
                    name=honeypot.name,
                    max_crashes=MAX_CONSECUTIVE_CRASHES,
                )
                break

            # 再起動前の待機
            logger.info(
                "honeypot.restarting",
                name=honeypot.name,
                delay=RESTART_DELAY,
            )
            await asyncio.sleep(RESTART_DELAY)

    # 停止処理
    try:
        await honeypot.stop()
    except Exception as e:
        logger.warning("honeypot.stop_error", name=honeypot.name, error=str(e))


async def run_all_honeypots() -> None:
    """全 Honeypot を起動し、シグナルで停止するまで実行する.

    SIGTERM / SIGINT を受信するとグレースフルシャットダウンする。
    """
    settings = get_settings()
    setup_logging(settings.log_level, settings.environment)

    logger.info("honeypot_manager.starting")

    # EventQueue（全 Honeypot で共有）
    event_queue = EventQueue()
    await event_queue.connect()

    # Honeypot インスタンスを作成
    honeypots: list[BaseHoneypot] = [
        SSHHoneypot(event_queue),
        HTTPHoneypot(event_queue),
    ]

    # シグナルハンドラー設定
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    def _signal_handler() -> None:
        logger.info("honeypot_manager.signal_received")
        shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

    # 各 Honeypot をバックグラウンドタスクとして起動
    tasks: list[asyncio.Task[None]] = []
    for honeypot in honeypots:
        task = asyncio.create_task(
            run_honeypot_with_restart(honeypot),
            name=f"honeypot-{honeypot.name}",
        )
        tasks.append(task)

    logger.info(
        "honeypot_manager.started",
        honeypots=[hp.name for hp in honeypots],
    )

    # シャットダウンシグナルを待つ
    await shutdown_event.wait()

    # グレースフルシャットダウン: 全タスクをキャンセル
    logger.info("honeypot_manager.shutting_down")
    for task in tasks:
        task.cancel()

    # 全タスクの完了を待つ
    await asyncio.gather(*tasks, return_exceptions=True)

    # EventQueue を閉じる
    await event_queue.close()

    logger.info("honeypot_manager.stopped")


def main() -> None:
    """Honeypot プロセスのメインエントリーポイント."""
    asyncio.run(run_all_honeypots())


if __name__ == "__main__":
    main()
