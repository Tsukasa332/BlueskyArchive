import httpx

from app.bluesky_client import BlueskyClient


def test_retry_after_seconds_is_honored():
    response = httpx.Response(429, headers={"Retry-After": "17"})
    assert BlueskyClient._retry_delay(response, 0) == 17


def test_retry_delay_falls_back_to_exponential_backoff():
    response = httpx.Response(503)
    assert BlueskyClient._retry_delay(response, 3) == 8


def test_list_records_reads_newest_records_first_by_default():
    client = BlueskyClient("alice.test", "app-password")
    client.did = "did:plc:alice"
    try:
        captured = {}

        def fake_request(method, path, **kwargs):
            captured.update({"method": method, "path": path, **kwargs})
            return {}

        client._request = fake_request

        client.list_records("app.bsky.feed.post")

        assert captured["params"]["reverse"] == "false"
    finally:
        client.close()
