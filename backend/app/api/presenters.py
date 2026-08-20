from datetime import datetime, timezone
from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from archive.bluesky_embed import (
    blob_cid,
    blob_cid_from_url,
    collection_from_at_uri,
    direct_image_items,
    direct_video_items,
    embedded_record,
    embedded_record_ref,
    hashtag_rows,
    label_values,
)
from archive.db.models import Actor, ExternalLink, MediaAsset, Post, PostMedia, Repost, SyncState
from app.schemas.posts import ActorOut, CaptionOut, EmbeddedRecordOut, ExternalLinkOut, HashtagFacetOut, MediaOut, PostOut


def media_for(post: Post) -> list[MediaOut]:
    return [
        MediaOut(
            cid=link.media_asset.cid,
            mime_type=link.media_asset.mime_type,
            size_bytes=link.media_asset.size_bytes,
            path="/media/" + link.media_asset.path.lstrip("/"),
            width=link.media_asset.width,
            height=link.media_asset.height,
            alt_text=link.media_asset.alt_text,
            media_type=link.media_asset.media_type,
            presentation=(link.media_asset.raw_json or {}).get("presentation") or "default",
            captions=[
                CaptionOut(
                    lang=caption.lang,
                    cid=caption.cid,
                    path="/media/" + caption.path.lstrip("/"),
                    mime_type=caption.mime_type,
                )
                for caption in sorted(link.media_asset.captions, key=lambda item: (item.lang, item.id))
            ],
        )
        for link in sorted(post.media_links, key=lambda item: item.position)
    ]


def did_from_at_uri(uri: str | None) -> str | None:
    if not uri or not uri.startswith("at://"):
        return None
    parts = uri.split("/")
    return parts[2] if len(parts) > 2 else None


def actor_for_uri(db: Session, uri: str | None) -> ActorOut | None:
    return actor_for_did(db, did_from_at_uri(uri))


def external_links_for(post: Post) -> list[ExternalLinkOut]:
    view_external = external_from_embed((post.raw_view_json or {}).get("embed") or {})
    return [
        external_link_out(
            {
                **((row.raw_json or {}).get("record") or row.raw_json or {}),
                **(
                    ((row.raw_json or {}).get("view") or {})
                    if isinstance(row.raw_json, dict)
                    else {}
                ),
                **(view_external if view_external.get("uri") == row.uri else {}),
                "uri": row.uri,
                "title": row.title or view_external.get("title"),
                "description": row.description or view_external.get("description"),
                "thumb_cid": row.thumb_cid,
            }
        )
        for row in sorted(post.external_links, key=lambda row: row.id)
    ]


def hashtag_facets(record: dict[str, Any]) -> list[HashtagFacetOut]:
    return [HashtagFacetOut(**row) for row in hashtag_rows(record)]


def actor_for_did(db: Session, did: str | None) -> ActorOut | None:
    if not did:
        return None
    actor_cache = db.info.setdefault("actor_cache", {})
    if did not in actor_cache:
        actor_cache[did] = db.scalar(select(Actor).where(Actor.did == did))
    actor = actor_cache[did]
    return actor_out(db, actor) if actor else None


def following_dids(db: Session) -> set[str]:
    cached = db.info.get("following_dids")
    if isinstance(cached, set):
        return cached
    state = db.scalar(select(SyncState).where(SyncState.source == "following"))
    dids = set((state.metadata_json or {}).get("following_dids") or []) if state else set()
    db.info["following_dids"] = dids
    return dids


def actor_out(db: Session, actor: Actor) -> ActorOut:
    return ActorOut.model_validate(actor).model_copy(
        update={"is_followed": actor.did in following_dids(db)}
    )


def actor_view_out(db: Session, data: dict[str, Any]) -> ActorOut:
    did = data.get("did", "")
    return ActorOut(
        did=did,
        handle=data.get("handle"),
        display_name=data.get("displayName"),
        avatar_cid=data.get("avatar"),
        is_followed=did in following_dids(db),
    )


def post_out(post: Post, db: Session) -> PostOut:
    return PostOut.model_validate(post).model_copy(
        update={
            "media": media_for(post),
            "external_links": external_links_for(post),
            "reply_root_author": actor_for_uri(db, post.reply_root_uri),
            "reply_parent_author": actor_for_uri(db, post.reply_parent_uri),
            "quote_author": actor_for_uri(db, post.quote_uri),
            "hashtags": hashtag_facets(post.raw_record_json or {}),
            "labels": label_values(post.raw_record_json, post.raw_view_json),
            "embedded_records": embedded_records_from(
                (post.raw_record_json or {}).get("embed"),
                (post.raw_view_json or {}).get("embed"),
            ),
        }
    )


def prime_post_context(db: Session, posts: list[Post]) -> None:
    dids = {post.author_did for post in posts}
    for post in posts:
        dids.update(
            filter(
                None,
                (
                    did_from_at_uri(post.reply_root_uri),
                    did_from_at_uri(post.reply_parent_uri),
                    did_from_at_uri(post.quote_uri),
                ),
            )
        )
    actors = db.scalars(select(Actor).where(Actor.did.in_(dids))).all() if dids else []
    actor_cache = db.info.setdefault("actor_cache", {})
    actor_cache.update(dict.fromkeys(dids))
    actor_cache.update({actor.did: actor for actor in actors})


def repost_out(repost: Repost, db: Session) -> dict[str, Any]:
    subject_view = (repost.raw_view_json or {}).get("subject_view") or {}
    subject_record = subject_view.get("record") or {}
    subject_author = subject_view.get("author") or {}
    archived_subject = (db.info.get("subject_post_cache") or {}).get(repost.subject_uri)
    if subject_author.get("did"):
        subject_author_out = actor_view_out(db, subject_author)
    elif archived_subject:
        subject_author_out = actor_out(db, archived_subject.author)
    else:
        subject_author_out = actor_for_uri(db, repost.subject_uri)
    archived_links = external_links_for(archived_subject) if archived_subject else []
    archived_media = [
        {
            "url": item.path,
            "thumb": None,
            "alt_text": item.alt_text,
            "media_type": item.media_type,
            "presentation": item.presentation,
            "captions": item.captions,
        }
        for item in (media_for(archived_subject) if archived_subject else [])
    ]
    return {
        "id": repost.id,
        "uri": repost.uri,
        "cid": repost.cid,
        "subject_uri": repost.subject_uri,
        "subject_cid": repost.subject_cid,
        "record_created_at": repost.record_created_at,
        "indexed_at": repost.indexed_at,
        "deleted": repost.deleted,
        "actor": actor_for_did(db, repost.actor_did),
        "subject_author": subject_author_out,
        "subject_text": subject_record.get("text") or (archived_subject.text if archived_subject else None),
        "subject_created_at": (
            parse_datetime(subject_record.get("createdAt"))
            or parse_datetime(subject_view.get("indexedAt"))
            or (archived_subject.record_created_at if archived_subject else None)
        ),
        "subject_media": archived_media or media_from_view(db, subject_view),
        "subject_external_links": (
            external_links_from_embed(subject_record.get("embed") or subject_view.get("embed") or {})
            or archived_links
        ),
        "subject_hashtags": hashtag_facets(subject_record),
        "subject_labels": label_values(subject_record, subject_view),
        "subject_embedded_records": embedded_records_from(
            subject_record.get("embed"),
            subject_view.get("embed"),
        ),
    }


def prime_repost_context(db: Session, reposts: list[Repost]) -> None:
    subject_uris = {repost.subject_uri for repost in reposts}
    subjects = (
        db.scalars(
            select(Post)
            .where(Post.uri.in_(subject_uris))
            .options(
                selectinload(Post.author),
                selectinload(Post.media_links).selectinload(PostMedia.media_asset),
                selectinload(Post.external_links),
            )
        ).all()
        if subject_uris
        else []
    )
    db.info["subject_post_cache"] = {post.uri: post for post in subjects}

    dids = {repost.actor_did for repost in reposts}
    cids: set[str] = set()
    for repost in reposts:
        subject_did = did_from_at_uri(repost.subject_uri)
        if subject_did:
            dids.add(subject_did)
        view = (repost.raw_view_json or {}).get("subject_view") or {}
        author_did = (view.get("author") or {}).get("did")
        if author_did:
            dids.add(author_did)
        cids.update(media_cids_from_view(view))
    actors = db.scalars(select(Actor).where(Actor.did.in_(dids))).all() if dids else []
    actor_cache = db.info.setdefault("actor_cache", {})
    actor_cache.update(dict.fromkeys(dids))
    actor_cache.update({actor.did: actor for actor in actors})
    assets = db.scalars(select(MediaAsset).where(MediaAsset.cid.in_(cids))).all() if cids else []
    media_cache = db.info.setdefault("media_cache", {})
    media_cache.update(dict.fromkeys(cids))
    media_cache.update({asset.cid: asset for asset in assets})


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def media_from_view(db: Session, view: dict[str, Any]) -> list[dict[str, Any]]:
    media: list[dict[str, Any]] = []
    embed = view.get("embed") or {}
    seen: set[str] = set()
    for image in direct_images(embed):
        url = image.get("fullsize") or image.get("thumb") or image.get("thumbnail")
        if url:
            cid = image_cid(image)
            dedupe_key = cid or url
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            local = local_media_url(db, cid)
            media.append(
                {
                    "url": local or url,
                    "thumb": local or image.get("thumb") or image.get("thumbnail"),
                    "alt_text": image.get("alt"),
                    "media_type": "image",
                }
            )
    for video in direct_videos(view):
        cid = video_cid(video)
        local_asset = local_media_asset(db, cid)
        local = "/media/" + local_asset.path.lstrip("/") if local_asset else None
        url = local or video.get("playlist") or video.get("thumbnail")
        dedupe_key = cid or url
        if not url or not dedupe_key or dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        media.append(
            {
                "url": url,
                "thumb": video.get("thumbnail"),
                "alt_text": video.get("alt"),
                "media_type": "video",
                "presentation": video.get("presentation") or "default",
                "captions": [
                    {
                        "lang": caption.lang,
                        "cid": caption.cid,
                        "path": "/media/" + caption.path.lstrip("/"),
                        "mime_type": caption.mime_type,
                    }
                    for caption in sorted(
                        getattr(local_asset, "captions", []) if local_asset else [],
                        key=lambda item: (item.lang, item.id),
                    )
                ],
            }
        )
    return media


def direct_images(embed: dict[str, Any]):
    yield from direct_image_items(embed)


def direct_video(embed: dict[str, Any]) -> dict[str, Any]:
    return next(direct_video_items(embed), {})


def direct_videos(view: dict[str, Any]):
    record_embed = (view.get("record") or {}).get("embed")
    yield from direct_video_items(record_embed)
    yield from direct_video_items(view.get("embed"))


def image_cid(image: dict[str, Any]) -> str | None:
    return (
        blob_cid(image.get("image"))
        or blob_cid_from_url(image.get("fullsize"))
        or blob_cid_from_url(image.get("thumb"))
        or blob_cid_from_url(image.get("thumbnail"))
        or image.get("cid")
    )


def video_cid(video: dict[str, Any]) -> str | None:
    return blob_cid(video.get("video")) or video.get("cid")


def media_cids_from_view(view: dict[str, Any]) -> set[str]:
    embed = view.get("embed") or {}
    cids = {cid for image in direct_images(embed) if (cid := image_cid(image))}
    cids.update(cid for video in direct_videos(view) if (cid := video_cid(video)))
    return cids


def local_media_url(db: Session, cid: str | None) -> str | None:
    asset = local_media_asset(db, cid)
    if not asset:
        return None
    return "/media/" + asset.path.lstrip("/")


def local_media_asset(db: Session, cid: str | None) -> MediaAsset | None:
    if not cid:
        return None
    media_cache = db.info.setdefault("media_cache", {})
    if cid not in media_cache:
        media_cache[cid] = db.scalar(select(MediaAsset).where(MediaAsset.cid == cid))
    asset = media_cache[cid]
    return asset


def external_links_from_embed(embed: dict[str, Any]) -> list[dict[str, Any]]:
    external = external_from_embed(embed)
    if not external:
        return []
    return [external_link_out(external).model_dump()]


def external_from_embed(embed: Any) -> dict[str, Any]:
    if not isinstance(embed, dict):
        return {}
    external = embed.get("external") or (embed.get("media") or {}).get("external")
    return external if isinstance(external, dict) else {}


def external_link_out(external: dict[str, Any]) -> ExternalLinkOut:
    profiles = []
    for profile in external.get("associatedProfiles") or []:
        if isinstance(profile, dict) and profile.get("did"):
            profiles.append(
                ActorOut(
                    did=profile["did"],
                    handle=profile.get("handle"),
                    display_name=profile.get("displayName"),
                    avatar_cid=profile.get("avatar"),
                )
            )
    return ExternalLinkOut(
        uri=external.get("uri", ""),
        title=external.get("title"),
        description=external.get("description"),
        thumb_cid=external.get("thumb_cid"),
        created_at=parse_datetime(external.get("createdAt")),
        updated_at=parse_datetime(external.get("updatedAt")),
        reading_time=external.get("readingTime"),
        source=external.get("source") if isinstance(external.get("source"), dict) else None,
        labels=[item for item in external.get("labels") or [] if isinstance(item, dict)],
        associated_refs=[
            item for item in external.get("associatedRefs") or [] if isinstance(item, dict)
        ],
        associated_profiles=profiles,
    )


def embedded_records_from(record_embed: Any, view_embed: Any) -> list[EmbeddedRecordOut]:
    ref = embedded_record_ref(record_embed, view_embed)
    uri = ref.get("uri")
    collection = collection_from_at_uri(uri)
    if not uri or not collection or collection == "app.bsky.feed.post":
        return []
    record = embedded_record(view_embed) or embedded_record(record_embed)
    title = (
        record.get("displayName")
        or record.get("name")
        or record.get("title")
        or record.get("handle")
    )
    return [
        EmbeddedRecordOut(
            uri=uri,
            cid=ref.get("cid"),
            collection=collection,
            record_type=record.get("$type"),
            title=title,
            description=record.get("description"),
        )
    ]
