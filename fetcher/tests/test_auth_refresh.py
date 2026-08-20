import httpx
import pytest

from app.bluesky_client import BlueskyClient


def response(status: int, url: str, body: dict) -> httpx.Response:
    return httpx.Response(status, json=body, request=httpx.Request("GET", url))


def test_expired_token_400_reauthenticates_and_retries_original_request_once():
    client = BlueskyClient("alice.test", "app-password")
    client.access_jwt = "expired"
    client.did = "did:plc:alice"
    calls = []
    replies = iter([
        response(400, "https://bsky.social/xrpc/app.bsky.graph.getFollows", {"error": "ExpiredToken"}),
        response(200, "https://bsky.social/xrpc/com.atproto.server.createSession", {"accessJwt": "fresh", "did": "did:plc:alice"}),
        response(200, "https://bsky.social/xrpc/app.bsky.graph.getFollows", {"follows": []}),
    ])

    def fake_request(method, url, **kwargs):
        calls.append((url, kwargs.get("headers", {})))
        return next(replies)

    client.client.request = fake_request
    try:
        assert client.get_follows("did:plc:alice") == {"follows": []}
        assert len(calls) == 3
        assert calls[0][1]["Authorization"] == "Bearer expired"
        assert calls[2][1]["Authorization"] == "Bearer fresh"
    finally:
        client.close()


def test_expired_token_after_reauthentication_does_not_loop():
    client = BlueskyClient("alice.test", "app-password")
    client.access_jwt = "expired"
    client.did = "did:plc:alice"
    replies = iter([
        response(400, "https://bsky.social/xrpc/app.bsky.graph.getFollows", {"error": "ExpiredToken"}),
        response(200, "https://bsky.social/xrpc/com.atproto.server.createSession", {"accessJwt": "fresh", "did": "did:plc:alice"}),
        response(400, "https://bsky.social/xrpc/app.bsky.graph.getFollows", {"error": "ExpiredToken"}),
    ])
    calls = 0

    def fake_request(method, url, **kwargs):
        nonlocal calls
        calls += 1
        return next(replies)

    client.client.request = fake_request
    try:
        with pytest.raises(httpx.HTTPStatusError):
            client.get_follows("did:plc:alice")
        assert calls == 3
    finally:
        client.close()


def test_stream_blob_reauthenticates_after_expired_token():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.url.path, request.headers.get("authorization")))
        if len(calls) == 1:
            return httpx.Response(400, json={"error": "ExpiredToken"})
        if request.url.path.endswith("createSession"):
            return httpx.Response(200, json={"accessJwt": "fresh", "did": "did:plc:alice"})
        return httpx.Response(200, content=b"streamed", headers={"content-type": "video/mp4"})

    client = BlueskyClient("alice.test", "app-password")
    client.client.close()
    client.client = httpx.Client(transport=httpx.MockTransport(handler))
    client.access_jwt = "expired"
    client.did = "did:plc:alice"
    try:
        with client.stream_blob("did:plc:alice", "bafkreivideo") as response:
            assert b"".join(response.iter_bytes()) == b"streamed"
        assert len(calls) == 3
        assert calls[0][1] == "Bearer expired"
        assert calls[2][1] == "Bearer fresh"
    finally:
        client.close()


def test_stream_blob_does_not_reauthenticate_more_than_once():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if request.url.path.endswith("createSession"):
            return httpx.Response(200, json={"accessJwt": "fresh", "did": "did:plc:alice"})
        return httpx.Response(400, json={"error": "ExpiredToken"})

    client = BlueskyClient("alice.test", "app-password")
    client.client.close()
    client.client = httpx.Client(transport=httpx.MockTransport(handler))
    client.access_jwt = "expired"
    client.did = "did:plc:alice"
    try:
        with pytest.raises(httpx.HTTPStatusError):
            with client.stream_blob("did:plc:alice", "bafkreivideo"):
                pass
        assert calls == 3
    finally:
        client.close()
