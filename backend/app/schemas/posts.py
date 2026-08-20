from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ActorOut(BaseModel):
    did: str
    handle: str | None = None
    display_name: str | None = None
    avatar_cid: str | None = None
    is_followed: bool = False

    model_config = ConfigDict(from_attributes=True)


class MediaOut(BaseModel):
    cid: str
    mime_type: str | None = None
    size_bytes: int | None = None
    path: str
    width: int | None = None
    height: int | None = None
    alt_text: str | None = None
    media_type: str
    presentation: str = "default"
    captions: list["CaptionOut"] = Field(default_factory=list)


class CaptionOut(BaseModel):
    lang: str
    cid: str
    path: str
    mime_type: str | None = None


class ExternalLinkOut(BaseModel):
    uri: str
    title: str | None = None
    description: str | None = None
    thumb_cid: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    reading_time: int | None = None
    source: dict[str, Any] | None = None
    labels: list[dict[str, Any]] = Field(default_factory=list)
    associated_refs: list[dict[str, Any]] = Field(default_factory=list)
    associated_profiles: list[ActorOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class RemoteMediaOut(BaseModel):
    url: str
    thumb: str | None = None
    alt_text: str | None = None
    media_type: str = "image"
    presentation: str = "default"
    captions: list[CaptionOut] = Field(default_factory=list)


class EmbeddedRecordOut(BaseModel):
    uri: str
    cid: str | None = None
    collection: str
    record_type: str | None = None
    title: str | None = None
    description: str | None = None


class HashtagFacetOut(BaseModel):
    tag: str
    start_byte: int | None = None
    end_byte: int | None = None


class PostOut(BaseModel):
    id: int
    uri: str
    cid: str | None = None
    text: str
    record_created_at: datetime | None = None
    indexed_at: datetime | None = None
    reply_root_uri: str | None = None
    reply_parent_uri: str | None = None
    quote_uri: str | None = None
    deleted: bool
    author: ActorOut
    reply_root_author: ActorOut | None = None
    reply_parent_author: ActorOut | None = None
    quote_author: ActorOut | None = None
    media: list[MediaOut] = Field(default_factory=list)
    external_links: list[ExternalLinkOut] = Field(default_factory=list)
    hashtags: list[HashtagFacetOut] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    embedded_records: list[EmbeddedRecordOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class PostDetailOut(PostOut):
    raw_record_json: dict[str, Any] | None = None
    raw_view_json: dict[str, Any] | None = None


class PostListOut(BaseModel):
    items: list[PostOut]
    total: int


class RepostOut(BaseModel):
    id: int
    uri: str
    cid: str | None = None
    subject_uri: str
    subject_cid: str | None = None
    record_created_at: datetime | None = None
    indexed_at: datetime | None = None
    deleted: bool
    actor: ActorOut | None = None
    subject_author: ActorOut | None = None
    subject_text: str | None = None
    subject_created_at: datetime | None = None
    subject_media: list[RemoteMediaOut] = Field(default_factory=list)
    subject_external_links: list[ExternalLinkOut] = Field(default_factory=list)
    subject_hashtags: list[HashtagFacetOut] = Field(default_factory=list)
    subject_labels: list[str] = Field(default_factory=list)
    subject_embedded_records: list[EmbeddedRecordOut] = Field(default_factory=list)


class RepostListOut(BaseModel):
    items: list[RepostOut]
    total: int


class CalendarYearOut(BaseModel):
    year: int
    count: int


class CalendarMonthOut(BaseModel):
    year: int
    month: int
    count: int


class CalendarDayOut(BaseModel):
    date: str
    count: int


class CalendarOut(BaseModel):
    years: list[CalendarYearOut] = Field(default_factory=list)
    months: list[CalendarMonthOut] = Field(default_factory=list)
    days: list[CalendarDayOut] = Field(default_factory=list)
