"""Track protocol processing version and video captions.

Revision ID: 0004_protocol_evolution
Revises: 0003_repost_hashtags
Create Date: 2026-07-30
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_protocol_evolution"
down_revision: str | None = "0003_repost_hashtags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "posts",
        sa.Column("archive_schema_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "reposts",
        sa.Column("archive_schema_version", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_table(
        "media_captions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "media_asset_id",
            sa.BigInteger(),
            sa.ForeignKey("media_assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("lang", sa.String(64), nullable=False),
        sa.Column("cid", sa.String(255), nullable=False),
        sa.Column("path", sa.String(1024), nullable=False),
        sa.Column("mime_type", sa.String(255)),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.UniqueConstraint(
            "media_asset_id",
            "lang",
            "cid",
            name="uq_media_captions_asset_lang_cid",
        ),
    )
    op.create_index("ix_media_captions_media_asset_id", "media_captions", ["media_asset_id"])
    op.create_index("ix_media_captions_cid", "media_captions", ["cid"])

    # Post-level tags have no byte offsets. Preserve facet rows and add only
    # tags that are not already represented case-insensitively.
    op.execute(
        """
        INSERT INTO hashtags (post_id, tag, start_byte, end_byte)
        SELECT p.id, ltrim(btrim(tag.value), '#'), NULL, NULL
        FROM posts AS p
        CROSS JOIN LATERAL jsonb_array_elements_text(
            CASE
                WHEN jsonb_typeof(p.raw_record_json -> 'tags') = 'array'
                THEN p.raw_record_json -> 'tags'
                ELSE '[]'::jsonb
            END
        ) AS tag(value)
        WHERE btrim(tag.value) <> ''
          AND NOT EXISTS (
              SELECT 1
              FROM hashtags AS h
              WHERE h.post_id = p.id
                AND lower(h.tag) = lower(ltrim(btrim(tag.value), '#'))
          )
        """
    )
    op.execute(
        """
        UPDATE posts
        SET quote_uri = COALESCE(
            raw_record_json #>> '{embed,record,record,uri}',
            raw_record_json #>> '{embed,record,uri}',
            raw_view_json #>> '{embed,record,record,uri}',
            raw_view_json #>> '{embed,record,uri}'
        )
        WHERE COALESCE(
            raw_record_json #>> '{embed,record,record,uri}',
            raw_record_json #>> '{embed,record,uri}',
            raw_view_json #>> '{embed,record,record,uri}',
            raw_view_json #>> '{embed,record,uri}'
        ) LIKE 'at://%/app.bsky.feed.post/%'
        """
    )
    op.execute(
        """
        UPDATE sync_states
        SET metadata_json = metadata_json - 'last_full_reconcile_at'
        WHERE source IN ('posts', 'reposts')
        """
    )


def downgrade() -> None:
    op.drop_table("media_captions")
    op.drop_column("reposts", "archive_schema_version")
    op.drop_column("posts", "archive_schema_version")
