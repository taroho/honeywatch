"""attack_events テーブルに分類カラム追加.

Revision ID: 002
Revises: 001
Create Date: 2026-08-31

Phase 2: 攻撃分類結果（attack_type, severity）を保存するカラムを追加する。
既存レコードとの互換性のため nullable とする。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 分類結果カラムを追加（nullable: 未分類の既存レコードを許容）
    op.add_column(
        "attack_events",
        sa.Column("attack_type", sa.String(30), nullable=True),
    )
    op.add_column(
        "attack_events",
        sa.Column("severity", sa.String(10), nullable=True),
    )

    # 集計クエリ高速化のためのインデックス
    op.create_index("ix_attack_events_attack_type", "attack_events", ["attack_type"])
    op.create_index("ix_attack_events_severity", "attack_events", ["severity"])


def downgrade() -> None:
    op.drop_index("ix_attack_events_severity", table_name="attack_events")
    op.drop_index("ix_attack_events_attack_type", table_name="attack_events")
    op.drop_column("attack_events", "severity")
    op.drop_column("attack_events", "attack_type")
