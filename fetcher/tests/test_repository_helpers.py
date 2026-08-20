from app.repository import hashtag_rows, rkey_from_uri
from archive.bluesky_embed import embedded_record_ref, label_values, quote_uri


def test_rkey_from_uri():
    assert rkey_from_uri("at://did:plc:abc/app.bsky.feed.post/123") == "123"


def test_hashtag_rows_extracts_tag_facets_with_utf8_offsets():
    record = {
        "facets": [{
            "index": {"byteStart": 4, "byteEnd": 17},
            "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": "日本語タグ"}],
        }]
    }
    assert hashtag_rows(record) == [{"tag": "日本語タグ", "start_byte": 4, "end_byte": 17}]


def test_hashtag_rows_ignores_mentions_and_empty_tags():
    record = {"facets": [{"features": [
        {"$type": "app.bsky.richtext.facet#mention", "did": "did:plc:test"},
        {"$type": "app.bsky.richtext.facet#tag", "tag": ""},
    ]}]}
    assert hashtag_rows(record) == []


def test_hashtag_rows_combines_post_tags_and_deduplicates_case_insensitively():
    record = {
        "facets": [{
            "index": {"byteStart": 0, "byteEnd": 5},
            "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": "Bluesky"}],
        }],
        "tags": ["#bluesky", "Archive"],
    }
    assert hashtag_rows(record) == [
        {"tag": "Bluesky", "start_byte": 0, "end_byte": 5},
        {"tag": "Archive", "start_byte": None, "end_byte": None},
    ]


def test_record_with_media_extracts_nested_post_quote():
    embed = {
        "$type": "app.bsky.embed.recordWithMedia",
        "record": {
            "$type": "app.bsky.embed.record",
            "record": {
                "uri": "at://did:plc:test/app.bsky.feed.post/quoted",
                "cid": "baf-quote",
            },
        },
        "media": {"$type": "app.bsky.embed.images", "images": []},
    }
    assert embedded_record_ref(embed) == {
        "uri": "at://did:plc:test/app.bsky.feed.post/quoted",
        "cid": "baf-quote",
    }
    assert quote_uri(embed) == "at://did:plc:test/app.bsky.feed.post/quoted"


def test_non_post_record_is_not_a_quote():
    embed = {
        "$type": "app.bsky.embed.record",
        "record": {"uri": "at://did:plc:test/app.bsky.graph.list/list1", "cid": "baf-list"},
    }
    assert quote_uri(embed) is None


def test_label_values_combines_self_and_view_labels():
    record = {"labels": {"values": [{"val": "sexual"}]}}
    view = {"labels": [{"val": "sexual"}, {"val": "nudity"}]}
    assert label_values(record, view) == ["sexual", "nudity"]
