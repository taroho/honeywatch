"""構造化ログ設定モジュール.

structlog を使用して JSON 形式の構造化ログを出力する。
開発環境ではカラー付きコンソール出力、本番環境では JSON 出力に切り替える。
"""

import logging
import sys

import structlog


def setup_logging(log_level: str = "INFO", environment: str = "development") -> None:
    """ログ設定を初期化する.

    Args:
        log_level: ログレベル（DEBUG, INFO, WARNING, ERROR, CRITICAL）
        environment: 環境名。development ならコンソール出力、production なら JSON 出力。
    """
    # 共通のプロセッサチェーン
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if environment == "development":
        # 開発環境: カラー付きコンソール出力
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer()
    else:
        # 本番環境: JSON 形式出力
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # 標準ライブラリ logging の設定
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # サードパーティライブラリのログレベルを抑制
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("asyncssh").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """名前付きロガーを取得する.

    Args:
        name: ロガー名（通常はモジュール名 __name__ を使用）

    Returns:
        structlog の BoundLogger インスタンス
    """
    return structlog.get_logger(name)
