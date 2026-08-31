"""SQLAlchemy データベースモデル定義.

attack_events テーブルを定義する。
タイムライン検索、IP 別検索、プロトコル別フィルタ用のインデックスを含む。
"""

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy モデルの基底クラス."""

    pass


class AttackEventModel(Base):
    """攻撃イベントテーブル.

    Honeypot が観測した1回の攻撃的アクセスを1レコードとして保存する。
    プロトコル固有のデータは raw_data カラムに JSON として格納する。
    """

    __tablename__ = "attack_events"

    # 主キー: UUID v4
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # イベント発生タイムスタンプ（Honeypot が記録した時刻）
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    # 送信元 IP アドレス（IPv6 対応のため最大45文字）
    source_ip: Mapped[str] = mapped_column(
        String(45),
        nullable=False,
        index=True,
    )

    # 送信元ポート番号
    source_port: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # 宛先ポート番号（Honeypot のリッスンポート）
    destination_port: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # プロトコル種別（ssh, http など）
    protocol: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        index=True,
    )

    # イベントタイプ（ssh_login_attempt, http_request など）
    event_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    # --- Phase 2 で追加: 分類結果 ---
    # 攻撃タイプ（brute_force, port_scan, http_scan 等）
    # 既存レコードとの互換性のため nullable（未分類は NULL）
    attack_type: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        index=True,
    )

    # 攻撃の深刻度（HIGH / MEDIUM / LOW）
    # 既存レコードとの互換性のため nullable（未判定は NULL）
    severity: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
        index=True,
    )

    # プロトコル固有データ（JSON 形式で格納）
    raw_data: Mapped[dict] = mapped_column(  # type: ignore[type-arg]
        JSON,
        nullable=False,
        default=dict,
    )

    # レコード作成日時（DB サーバー側のタイムスタンプ）
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # 複合インデックス: タイムライン + プロトコル別表示の高速化
    __table_args__ = (
        Index("ix_attack_events_timestamp_protocol", "timestamp", "protocol"),
    )

    def __repr__(self) -> str:
        """デバッグ用の文字列表現."""
        return (
            f"<AttackEvent(id={self.id}, protocol={self.protocol}, "
            f"source_ip={self.source_ip}, event_type={self.event_type})>"
        )
