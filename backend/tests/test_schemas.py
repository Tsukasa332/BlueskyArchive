import os

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost/test")

from app.api.presenters import blob_cid_from_url, embedded_records_from, hashtag_facets, image_cid
from app.schemas.posts import CalendarOut, HashtagFacetOut


def test_calendar_schema_defaults():
    calendar = CalendarOut()
    assert calendar.years == []
    assert calendar.months == []
    assert calendar.days == []


def test_repost_media_cid_from_bsky_cdn_url_strips_format_suffix():
    assert (
        blob_cid_from_url("https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:example/bafkreig123@jpeg")
        == "bafkreig123"
    )


def test_repost_media_cid_prefers_blob_ref():
    assert image_cid({"image": {"ref": {"$link": "bafkreifromblob"}}, "fullsize": "https://cdn.bsky.app/img/feed_fullsize/plain/did:plc:example/bafkreifromurl@jpeg"}) == "bafkreifromblob"


def test_hashtag_facets_preserve_utf8_byte_offsets():
    record = {"facets": [{
        "index": {"byteStart": 3, "byteEnd": 16},
        "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": "日本語タグ"}],
    }]}
    facets = hashtag_facets(record)
    assert facets == [HashtagFacetOut(tag="日本語タグ", start_byte=3, end_byte=16)]
    assert facets[0].model_dump() == {"tag": "日本語タグ", "start_byte": 3, "end_byte": 16}


def test_hashtag_facets_include_post_level_tags_without_offsets():
    assert hashtag_facets({"tags": ["Archive"]}) == [
        HashtagFacetOut(tag="Archive", start_byte=None, end_byte=None)
    ]


def test_non_post_embedded_record_is_exposed_as_generic_record():
    records = embedded_records_from(
        {
            "$type": "app.bsky.embed.record",
            "record": {
                "uri": "at://did:plc:test/app.bsky.graph.list/list1",
                "cid": "baf-list",
            },
        },
        {
            "$type": "app.bsky.embed.record#view",
            "record": {
                "uri": "at://did:plc:test/app.bsky.graph.list/list1",
                "cid": "baf-list",
                "$type": "app.bsky.embed.record#viewRecord",
                "name": "Example list",
                "description": "Description",
            },
        },
    )
    assert records[0].collection == "app.bsky.graph.list"
    assert records[0].title == "Example list"
