"""Add searchable hashtags for archived repost subjects.

Revision ID: 0003_repost_hashtags
Revises: 0002_sync_integrity
Create Date: 2026-07-10
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_repost_hashtags"
down_revision: str | None = "0002_sync_integrity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "repost_hashtags",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("repost_id", sa.BigInteger(), sa.ForeignKey("reposts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tag", sa.String(255), nullable=False),
        sa.Column("start_byte", sa.Integer()),
        sa.Column("end_byte", sa.Integer()),
        sa.UniqueConstraint("repost_id", "tag", "start_byte", "end_byte", name="uq_repost_hashtags_facet"),
    )
    op.create_index("ix_repost_hashtags_repost_id", "repost_hashtags", ["repost_id"])
    op.create_index("ix_repost_hashtags_tag", "repost_hashtags", ["tag"])
    op.execute("CREATE INDEX ix_repost_hashtags_tag_lower ON repost_hashtags (lower(tag))")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_repost_hashtags_tag_lower")
    op.drop_table("repost_hashtags")
