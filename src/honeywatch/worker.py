"""Event Worker エントリーポイント.

`python -m honeywatch.worker` で起動する。
"""

import asyncio
import os

from honeywatch.tasks.workers import run_worker


def main() -> None:
    """Worker プロセスを起動する."""
    consumer_name = os.environ.get("WORKER_NAME", "worker-1")
    asyncio.run(run_worker(consumer_name=consumer_name))


if __name__ == "__main__":
    main()
