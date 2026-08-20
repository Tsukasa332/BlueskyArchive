from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class Actor(Base, TimestampMixin):
    __tablename__ = "actors"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    did: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    handle: Mapped[str | None] = mapped_column(String(255), index=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    avatar_cid: Mapped[str | None] = mapped_column(String(255))
    banner_cid: Mapped[str | None] = mapped_column(String(255))
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class Post(Base, TimestampMixin):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    uri: Mapped[str] = mapped_column(String(512), unique=True, nullable=False, index=True)
    cid: Mapped[str | None] = mapped_column(String(255), index=True)
    author_did: Mapped[str] = mapped_column(String(255), ForeignKey("actors.did"), nullable=False, index=True)
    rkey: Mapped[str | None] = mapped_column(String(255), index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    langs: Mapped[list[str] | None] = mapped_column(JSONB)
    reply_root_uri: Mapped[str | None] = mapped_column(String(512), index=True)
    reply_parent_uri: Mapped[str | None] = mapped_column(String(512), index=True)
    quote_uri: Mapped[str | None] = mapped_column(String(512), index=True)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    record_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    repo_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    archive_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raw_record_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    raw_view_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    search_vector: Mapped[str | None] = mapped_column(TSVECTOR)

    author: Mapped[Actor] = relationship()
    media_links: Mapped[list["PostMedia"]] = relationship(back_populates="post", cascade="all, delete-orphan")
    external_links: Mapped[list["ExternalLink"]] = relationship(cascade="all, delete-orphan")
    embeds: Mapped[list["Embed"]] = relationship(cascade="all, delete-orphan")

    __table_args__ = (Index("ix_posts_search_vector", "search_vector", postgresql_using="gin"),)


class PostVersion(Base):
    __tablename__ = "post_versions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    cid: Mapped[str | None] = mapped_column(String(255), index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    raw_record_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("post_id", "cid", name="uq_post_versions_post_id_cid"),)


class Repost(Base, TimestampMixin):
    __tablename__ = "reposts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    uri: Mapped[str] = mapped_column(String(512), unique=True, nullable=False, index=True)
    cid: Mapped[str | None] = mapped_column(String(255), index=True)
    actor_did: Mapped[str] = mapped_column(String(255), ForeignKey("actors.did"), nullable=False, index=True)
    subject_uri: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    subject_cid: Mapped[str | None] = mapped_column(String(255))
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    record_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    repo_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    archive_schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raw_record_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    raw_view_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class RepostHashtag(Base):
    __tablename__ = "repost_hashtags"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    repost_id: Mapped[int] = mapped_column(ForeignKey("reposts.id", ondelete="CASCADE"), nullable=False, index=True)
    tag: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    start_byte: Mapped[int | None] = mapped_column(Integer)
    end_byte: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        UniqueConstraint("repost_id", "tag", "start_byte", "end_byte", name="uq_repost_hashtags_facet"),
    )


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    cid: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    mime_type: Mapped[str | None] = mapped_column(String(255))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    alt_text: Mapped[str | None] = mapped_column(Text)
    media_type: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown", index=True)
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    captions: Mapped[list["MediaCaption"]] = relationship(cascade="all, delete-orphan")


class MediaCaption(Base):
    __tablename__ = "media_captions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    media_asset_id: Mapped[int] = mapped_column(ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    lang: Mapped[str] = mapped_column(String(64), nullable=False)
    cid: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(255))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)

    __table_args__ = (
        UniqueConstraint("media_asset_id", "lang", "cid", name="uq_media_captions_asset_lang_cid"),
    )


class PostMedia(Base):
    __tablename__ = "post_media"

    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True)
    media_asset_id: Mapped[int] = mapped_column(ForeignKey("media_assets.id", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    post: Mapped[Post] = relationship(back_populates="media_links")
    media_asset: Mapped[MediaAsset] = relationship()


class Embed(Base):
    __tablename__ = "embeds"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    embed_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    uri: Mapped[str | None] = mapped_column(String(1024))
    cid: Mapped[str | None] = mapped_column(String(255))
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ExternalLink(Base):
    __tablename__ = "external_links"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    uri: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    thumb_cid: Mapped[str | None] = mapped_column(String(255))
    raw_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Mention(Base):
    __tablename__ = "mentions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    did: Mapped[str | None] = mapped_column(String(255), index=True)
    handle: Mapped[str | None] = mapped_column(String(255), index=True)
    text: Mapped[str | None] = mapped_column(String(255))
    start_byte: Mapped[int | None] = mapped_column(Integer)
    end_byte: Mapped[int | None] = mapped_column(Integer)


class Hashtag(Base):
    __tablename__ = "hashtags"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    tag: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    start_byte: Mapped[int | None] = mapped_column(Integer)
    end_byte: Mapped[int | None] = mapped_column(Integer)


class SyncState(Base, TimestampMixin):
    __tablename__ = "sync_states"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    cursor: Mapped[str | None] = mapped_column(Text)
    last_seen_indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running", index=True)
    fetched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
