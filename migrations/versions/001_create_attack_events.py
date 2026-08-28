"""attack_events テーブル作成.

Revision ID: 001
Revises:
Create Date: 2026-08-28

初期マイグレーション: 攻撃イベントを保存するメインテーブルを作成する。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "attack_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_ip", sa.String(45), nullable=False),
        sa.Column("source_port", sa.Integer(), nullable=False),
        sa.Column("destination_port", sa.Integer(), nullable=False),
        sa.Column("protocol", sa.String(10), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # 個別インデックス
    op.create_index("ix_attack_events_timestamp", "attack_events", ["timestamp"])
    op.create_index("ix_attack_events_source_ip", "attack_events", ["source_ip"])
    op.create_index("ix_attack_events_protocol", "attack_events", ["protocol"])
    op.create_index("ix_attack_events_event_type", "attack_events", ["event_type"])

    # 複合インデックス: タイムライン + プロトコル別表示
    op.create_index(
        "ix_attack_events_timestamp_protocol",
        "attack_events",
        ["timestamp", "protocol"],
    )


def downgrade() -> None:
    op.drop_index("ix_attack_events_timestamp_protocol", table_name="attack_events")
    op.drop_index("ix_attack_events_event_type", table_name="attack_events")
    op.drop_index("ix_attack_events_protocol", table_name="attack_events")
    op.drop_index("ix_attack_events_source_ip", table_name="attack_events")
    op.drop_index("ix_attack_events_timestamp", table_name="attack_events")
    op.drop_table("attack_events")
