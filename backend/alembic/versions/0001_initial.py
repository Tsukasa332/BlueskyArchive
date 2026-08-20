"""Initial schema frozen at revision 0001.

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-27
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = postgresql.JSONB(astext_type=sa.Text())


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.create_table("actors",
        sa.Column("id", sa.BigInteger(), primary_key=True), sa.Column("did", sa.String(255), nullable=False),
        sa.Column("handle", sa.String(255)), sa.Column("display_name", sa.String(255)), sa.Column("description", sa.Text()),
        sa.Column("avatar_cid", sa.String(255)), sa.Column("banner_cid", sa.String(255)), sa.Column("raw_json", JSON, nullable=False),
        *_timestamps(), sa.UniqueConstraint("did"))
    op.create_index("ix_actors_did", "actors", ["did"])
    op.create_index("ix_actors_handle", "actors", ["handle"])

    op.create_table("posts",
        sa.Column("id", sa.BigInteger(), primary_key=True), sa.Column("uri", sa.String(512), nullable=False),
        sa.Column("cid", sa.String(255)), sa.Column("author_did", sa.String(255), sa.ForeignKey("actors.did"), nullable=False),
        sa.Column("rkey", sa.String(255)), sa.Column("text", sa.Text(), nullable=False), sa.Column("langs", JSON),
        sa.Column("reply_root_uri", sa.String(512)), sa.Column("reply_parent_uri", sa.String(512)), sa.Column("quote_uri", sa.String(512)),
        sa.Column("indexed_at", sa.DateTime(timezone=True)), sa.Column("record_created_at", sa.DateTime(timezone=True)),
        sa.Column("deleted", sa.Boolean(), nullable=False), sa.Column("raw_record_json", JSON, nullable=False),
        sa.Column("raw_view_json", JSON, nullable=False), sa.Column("search_vector", postgresql.TSVECTOR()),
        *_timestamps(), sa.UniqueConstraint("uri"))
    for column in ("uri", "cid", "author_did", "rkey", "reply_root_uri", "reply_parent_uri", "quote_uri", "indexed_at", "record_created_at", "deleted"):
        op.create_index(f"ix_posts_{column}", "posts", [column])
    op.create_index("ix_posts_search_vector", "posts", ["search_vector"], postgresql_using="gin")

    op.create_table("post_versions",
        sa.Column("id", sa.BigInteger(), primary_key=True), sa.Column("post_id", sa.BigInteger(), sa.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cid", sa.String(255)), sa.Column("text", sa.Text(), nullable=False), sa.Column("raw_record_json", JSON, nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("post_id", "cid", name="uq_post_versions_post_id_cid"))
    op.create_index("ix_post_versions_post_id", "post_versions", ["post_id"])
    op.create_index("ix_post_versions_cid", "post_versions", ["cid"])

    op.create_table("reposts",
        sa.Column("id", sa.BigInteger(), primary_key=True), sa.Column("uri", sa.String(512), nullable=False), sa.Column("cid", sa.String(255)),
        sa.Column("actor_did", sa.String(255), sa.ForeignKey("actors.did"), nullable=False), sa.Column("subject_uri", sa.String(512), nullable=False),
        sa.Column("subject_cid", sa.String(255)), sa.Column("indexed_at", sa.DateTime(timezone=True)),
        sa.Column("record_created_at", sa.DateTime(timezone=True)), sa.Column("deleted", sa.Boolean(), nullable=False),
        sa.Column("raw_record_json", JSON, nullable=False), sa.Column("raw_view_json", JSON, nullable=False), *_timestamps(), sa.UniqueConstraint("uri"))
    for column in ("uri", "cid", "actor_did", "subject_uri", "indexed_at", "record_created_at", "deleted"):
        op.create_index(f"ix_reposts_{column}", "reposts", [column])

    op.create_table("media_assets",
        sa.Column("id", sa.BigInteger(), primary_key=True), sa.Column("cid", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(255)), sa.Column("size_bytes", sa.BigInteger()), sa.Column("path", sa.String(1024), nullable=False),
        sa.Column("width", sa.Integer()), sa.Column("height", sa.Integer()), sa.Column("alt_text", sa.Text()),
        sa.Column("media_type", sa.String(32), nullable=False), sa.Column("raw_json", JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False), sa.UniqueConstraint("cid"))
    op.create_index("ix_media_assets_cid", "media_assets", ["cid"])
    op.create_index("ix_media_assets_media_type", "media_assets", ["media_type"])

    op.create_table("post_media",
        sa.Column("post_id", sa.BigInteger(), sa.ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("media_asset_id", sa.BigInteger(), sa.ForeignKey("media_assets.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("position", sa.Integer(), nullable=False))

    op.create_table("embeds",
        sa.Column("id", sa.BigInteger(), primary_key=True), sa.Column("post_id", sa.BigInteger(), sa.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("embed_type", sa.String(128), nullable=False), sa.Column("uri", sa.String(1024)), sa.Column("cid", sa.String(255)),
        sa.Column("raw_json", JSON, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_embeds_post_id", "embeds", ["post_id"])
    op.create_index("ix_embeds_embed_type", "embeds", ["embed_type"])

    op.create_table("external_links",
        sa.Column("id", sa.BigInteger(), primary_key=True), sa.Column("post_id", sa.BigInteger(), sa.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uri", sa.String(2048), nullable=False), sa.Column("title", sa.Text()), sa.Column("description", sa.Text()),
        sa.Column("thumb_cid", sa.String(255)), sa.Column("raw_json", JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_external_links_post_id", "external_links", ["post_id"])

    op.create_table("mentions",
        sa.Column("id", sa.BigInteger(), primary_key=True), sa.Column("post_id", sa.BigInteger(), sa.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("did", sa.String(255)), sa.Column("handle", sa.String(255)), sa.Column("text", sa.String(255)),
        sa.Column("start_byte", sa.Integer()), sa.Column("end_byte", sa.Integer()))
    for column in ("post_id", "did", "handle"):
        op.create_index(f"ix_mentions_{column}", "mentions", [column])

    op.create_table("hashtags",
        sa.Column("id", sa.BigInteger(), primary_key=True), sa.Column("post_id", sa.BigInteger(), sa.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tag", sa.String(255), nullable=False), sa.Column("start_byte", sa.Integer()), sa.Column("end_byte", sa.Integer()))
    op.create_index("ix_hashtags_post_id", "hashtags", ["post_id"])
    op.create_index("ix_hashtags_tag", "hashtags", ["tag"])

    op.create_table("sync_states",
        sa.Column("id", sa.BigInteger(), primary_key=True), sa.Column("source", sa.String(128), nullable=False), sa.Column("cursor", sa.Text()),
        sa.Column("last_seen_indexed_at", sa.DateTime(timezone=True)), sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_at", sa.DateTime(timezone=True)), sa.Column("metadata_json", JSON, nullable=False), *_timestamps(), sa.UniqueConstraint("source"))
    op.create_index("ix_sync_states_last_seen_indexed_at", "sync_states", ["last_seen_indexed_at"])

    op.create_table("sync_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True), sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)), sa.Column("status", sa.String(32), nullable=False),
        sa.Column("fetched_count", sa.Integer(), nullable=False), sa.Column("inserted_count", sa.Integer(), nullable=False),
        sa.Column("updated_count", sa.Integer(), nullable=False), sa.Column("deleted_count", sa.Integer(), nullable=False), sa.Column("error_message", sa.Text()))
    op.create_index("ix_sync_runs_status", "sync_runs", ["status"])

    op.execute("""
    CREATE OR REPLACE FUNCTION posts_search_vector_update() RETURNS trigger AS $$
    BEGIN
      NEW.search_vector := setweight(to_tsvector('simple', coalesce(NEW.text, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce((SELECT string_agg(tag, ' ') FROM hashtags WHERE post_id = NEW.id), '')), 'B') ||
        setweight(to_tsvector('simple', coalesce((SELECT string_agg(coalesce(handle, text, did), ' ') FROM mentions WHERE post_id = NEW.id), '')), 'C');
      RETURN NEW;
    END $$ LANGUAGE plpgsql
    """)
    op.execute("CREATE TRIGGER posts_search_vector_trigger BEFORE INSERT OR UPDATE OF text ON posts FOR EACH ROW EXECUTE FUNCTION posts_search_vector_update()")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS posts_search_vector_trigger ON posts")
    op.execute("DROP FUNCTION IF EXISTS posts_search_vector_update")
    for table in ("sync_runs", "sync_states", "hashtags", "mentions", "external_links", "embeds", "post_media", "media_assets", "reposts", "post_versions", "posts", "actors"):
        op.drop_table(table)
