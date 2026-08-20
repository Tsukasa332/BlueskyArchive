"""Add repository scan markers and Japanese substring search index.

Revision ID: 0002_sync_integrity
Revises: 0001_initial
Create Date: 2026-07-10
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0002_sync_integrity"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS repo_seen_at TIMESTAMPTZ")
    op.execute("ALTER TABLE reposts ADD COLUMN IF NOT EXISTS repo_seen_at TIMESTAMPTZ")
    op.execute("CREATE INDEX IF NOT EXISTS ix_posts_repo_seen_at ON posts (repo_seen_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_reposts_repo_seen_at ON reposts (repo_seen_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_posts_text_trgm ON posts USING gin (text gin_trgm_ops)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_hashtags_tag_trgm ON hashtags USING gin (tag gin_trgm_ops)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mentions_handle_trgm ON mentions USING gin (handle gin_trgm_ops)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mentions_text_trgm ON mentions USING gin (text gin_trgm_ops)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mentions_did_trgm ON mentions USING gin (did gin_trgm_ops)")
    op.execute("""
        UPDATE sync_states
        SET metadata_json = coalesce(metadata_json, '{}'::jsonb) || jsonb_build_object(
            'newest_rkey', (SELECT max(rkey) FROM posts),
            'last_full_reconcile_at', now()::text
        )
        WHERE source = 'posts' AND NOT (coalesce(metadata_json, '{}'::jsonb) ? 'newest_rkey')
    """)
    op.execute("""
        UPDATE sync_states
        SET metadata_json = coalesce(metadata_json, '{}'::jsonb) || jsonb_build_object(
            'newest_rkey', (SELECT max(split_part(uri, '/', 5)) FROM reposts),
            'last_full_reconcile_at', now()::text
        )
        WHERE source = 'reposts' AND NOT (coalesce(metadata_json, '{}'::jsonb) ? 'newest_rkey')
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_posts_text_trgm")
    op.execute("DROP INDEX IF EXISTS ix_hashtags_tag_trgm")
    op.execute("DROP INDEX IF EXISTS ix_mentions_handle_trgm")
    op.execute("DROP INDEX IF EXISTS ix_mentions_text_trgm")
    op.execute("DROP INDEX IF EXISTS ix_mentions_did_trgm")
    op.execute("DROP INDEX IF EXISTS ix_reposts_repo_seen_at")
    op.execute("DROP INDEX IF EXISTS ix_posts_repo_seen_at")
    op.execute("ALTER TABLE reposts DROP COLUMN IF EXISTS repo_seen_at")
    op.execute("ALTER TABLE posts DROP COLUMN IF EXISTS repo_seen_at")
