import logging
import time
from contextlib import contextmanager
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from typing import Any, Iterator

import httpx

logger = logging.getLogger(__name__)


class BlueskyClient:
    def __init__(self, identifier: str, app_password: str, timeout: float = 30.0, service_url: str = "https://bsky.social") -> None:
        self.identifier = identifier
        self.app_password = app_password
        self.service_url = service_url.rstrip("/")
        self.client = httpx.Client(timeout=timeout, follow_redirects=True)
        self.access_jwt: str | None = None
        self.did: str | None = None

    def close(self) -> None:
        self.client.close()

    def login(self) -> None:
        if self.access_jwt and self.did:
            return
        self._create_session()

    def _create_session(self) -> None:
        data = self._request("POST", "/xrpc/com.atproto.server.createSession", json={"identifier": self.identifier, "password": self.app_password}, auth=False)
        self.access_jwt = data["accessJwt"]
        self.did = data["did"]
        logger.info("logged in as %s", self.did)

    def list_records(self, collection: str, cursor: str | None = None, limit: int = 100, *, reverse: bool = False) -> dict[str, Any]:
        if self.did is None:
            raise RuntimeError("login must be called before list_records")
        params = {"repo": self.did, "collection": collection, "limit": limit, "reverse": str(reverse).lower()}
        if cursor:
            params["cursor"] = cursor
        return self._request("GET", "/xrpc/com.atproto.repo.listRecords", params=params)

    def get_record(self, repo: str, collection: str, rkey: str) -> dict[str, Any]:
        return self._request("GET", "/xrpc/com.atproto.repo.getRecord", params={"repo": repo, "collection": collection, "rkey": rkey})

    def resolve_handle(self, handle: str) -> str:
        data = self._request("GET", "/xrpc/com.atproto.identity.resolveHandle", params={"handle": handle}, auth=False)
        return data["did"]

    def get_posts(self, uris: list[str]) -> dict[str, Any]:
        params = [("uris", uri) for uri in uris]
        return self._request("GET", "/xrpc/app.bsky.feed.getPosts", params=params)

    def get_profile(self, actor: str) -> dict[str, Any]:
        return self._request("GET", "/xrpc/app.bsky.actor.getProfile", params={"actor": actor})

    def get_follows(self, actor: str, cursor: str | None = None, limit: int = 100) -> dict[str, Any]:
        params = {"actor": actor, "limit": limit}
        if cursor:
            params["cursor"] = cursor
        return self._request("GET", "/xrpc/app.bsky.graph.getFollows", params=params)

    @contextmanager
    def stream_blob(self, did: str, cid: str) -> Iterator[httpx.Response]:
        with self._stream_request("GET", "/xrpc/com.atproto.sync.getBlob", params={"did": did, "cid": cid}) as response:
            yield response

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_jwt}"} if self.access_jwt else {}

    def _request(self, method: str, path: str, *, auth: bool = True, **kwargs: Any) -> dict[str, Any]:
        response = self._raw_request(method, path, auth=auth, **kwargs)
        return response.json()

    def _raw_request(self, method: str, path: str, *, auth: bool = True, **kwargs: Any) -> httpx.Response:
        url = f"{self.service_url}{path}"
        headers = kwargs.pop("headers", {})
        if auth:
            headers = {**headers, **self._headers()}
        last_error: Exception | None = None
        reauthenticated = False
        for attempt in range(5):
            try:
                response = self.client.request(method, url, headers=headers, **kwargs)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_error = exc
                sleep = min(60, 2 ** attempt)
                logger.warning("Bluesky API request failed attempt=%s sleep=%s error=%s", attempt + 1, sleep, exc)
                time.sleep(sleep)
                continue

            expired_token = response.status_code == 400 and self._error_code(response) == "ExpiredToken"
            if auth and not reauthenticated and (response.status_code == 401 or expired_token):
                self.access_jwt = None
                self.did = None
                self._create_session()
                headers = {**headers, **self._headers()}
                response = self.client.request(method, url, headers=headers, **kwargs)
                reauthenticated = True
            if response.status_code in {429, 500, 502, 503, 504}:
                sleep = self._retry_delay(response, attempt)
                logger.warning("retryable Bluesky API error status=%s sleep=%s", response.status_code, sleep)
                time.sleep(sleep)
                continue
            if response.is_error:
                logger.warning("Bluesky API error status=%s body=%s", response.status_code, response.text[:500])
            response.raise_for_status()
            return response
        if last_error:
            raise last_error
        raise RuntimeError("Bluesky API request failed")

    @contextmanager
    def _stream_request(self, method: str, path: str, *, auth: bool = True, **kwargs: Any) -> Iterator[httpx.Response]:
        url = f"{self.service_url}{path}"
        headers = kwargs.pop("headers", {})
        if auth:
            headers = {**headers, **self._headers()}
        last_error: Exception | None = None
        reauthenticated = False
        for attempt in range(5):
            response: httpx.Response | None = None
            try:
                request = self.client.build_request(method, url, headers=headers, **kwargs)
                response = self.client.send(request, stream=True)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                last_error = exc
                sleep = min(60, 2 ** attempt)
                logger.warning("Bluesky API stream request failed attempt=%s sleep=%s error=%s", attempt + 1, sleep, exc)
                time.sleep(sleep)
                continue

            if response.status_code == 400:
                response.read()
            expired_token = response.status_code == 400 and self._error_code(response) == "ExpiredToken"
            if auth and not reauthenticated and (response.status_code == 401 or expired_token):
                response.close()
                self.access_jwt = None
                self.did = None
                self._create_session()
                headers = {**headers, **self._headers()}
                reauthenticated = True
                continue
            if response.status_code in {429, 500, 502, 503, 504}:
                sleep = self._retry_delay(response, attempt)
                response.close()
                logger.warning("retryable Bluesky API stream error status=%s sleep=%s", response.status_code, sleep)
                time.sleep(sleep)
                continue
            if response.is_error:
                response.read()
                logger.warning("Bluesky API error status=%s body=%s", response.status_code, response.text[:500])
                try:
                    response.raise_for_status()
                finally:
                    response.close()
            try:
                yield response
            finally:
                response.close()
            return
        if last_error:
            raise last_error
        raise RuntimeError("Bluesky API stream request failed")

    @staticmethod
    def _error_code(response: httpx.Response) -> str | None:
        try:
            body = response.json()
        except (ValueError, TypeError):
            return None
        return body.get("error") if isinstance(body, dict) else None

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        value = response.headers.get("retry-after")
        if value:
            try:
                return min(300.0, max(0.0, float(value)))
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(value)
                    if retry_at.tzinfo is None:
                        retry_at = retry_at.replace(tzinfo=timezone.utc)
                    return min(300.0, max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds()))
                except (TypeError, ValueError):
                    pass
        return float(min(60, 2 ** attempt))
