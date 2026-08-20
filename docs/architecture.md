# BlueskyArchive Architecture

English | [日本語](architecture.ja.md)

## 1. Purpose

BlueskyArchive continuously retrieves the posts and reposts of one Bluesky account and provides a searchable personal archive with PostgreSQL as the system of record.

The public edition enforces these boundaries:

- It does not include the network-wide image-search viewer or public block-list feature.
- It does not store images, videos, or video captions created by other people.
- It stores owner media only when `SAVE_OWN_MEDIA=true`.
- Even when owner-media storage is enabled, only directly attached media is eligible; media inside quoted posts is excluded.
- It retains raw JSON to support future protocol changes.
- Its user interface defaults to English and can switch between English and Japanese without changing API or database data.

## 2. Runtime architecture

| Service | Responsibility | Connections |
|---|---|---|
| `nginx` | HTTP entry point, frontend/API/owner-media routing, rate limits, security headers | Frontend, backend, `media/` |
| `frontend` | React/Vite browser interface | Backend through browser requests to `/api` |
| `backend` | Timeline, search, calendar, analytics, and manual sync requests | PostgreSQL |
| `fetcher` | Repository retrieval, record interpretation, database updates, optional owner-media storage | Bluesky API, PostgreSQL, `media/` |
| `postgres` | Archive, search indexes, sync state, and run history | Database network |
| `db-migrate` | Alembic migrations | PostgreSQL |
| `db-grants` | Applies and verifies backend/fetcher role privileges | PostgreSQL |

Startup ordering is `postgres` → `db-migrate` → `db-grants` → `backend` / `fetcher`. The frontend and database networks are separate, and only the backend joins both.

## 3. Synchronization and persistence

1. The fetcher signs in with an App Password and resolves the archived account's DID.
2. It retrieves post and repost records from the account's repository, newest first.
3. It interprets post views, actors, facets, labels, and embeds.
4. It upserts posts and reposts into separate tables.
5. It stores directly attached media only when `SAVE_OWN_MEDIA=true` and the post's `author_did` matches the authenticated DID.
6. It retains the repost source view as display metadata but does not store its media files.
7. It updates cursors, sync results, and full-reconciliation timestamps.

Media eligibility is centralized in `SyncService._save_media_for_post`. It does not recurse into quote embeds and only accepts direct attachments returned by `shared/archive/bluesky_embed.py`. The public edition contains no path that stores repost-source media.

`SAVE_OWN_MEDIA=false` stops new media downloads. It does not delete existing files or database rows, so migrations from older environments require a separate data audit.

## 4. Presentation and localization

The frontend treats URL query parameters as navigation state and retrieves timelines, search results, calendars, navigation summaries, and analytics from the backend. The backend applies stable ordering before pagination, and the frontend groups entries by date.

The media API schema refers only to locally stored owner media. Repost-source media metadata is not presented as stored media when no local asset exists.

Language is presentation-only:

- English is the default.
- English and Japanese strings are bundled with the frontend.
- The selected language is stored in browser localStorage with the other display settings.
- The document `lang` attribute, visible labels, date formatting, relative times, and accessible labels update together.
- Language selection is not sent to the backend and does not alter archive records.

## 5. Source responsibilities

### Frontend

- `frontend/src/main.tsx`: routes, filters, page state, and language switching
- `frontend/src/i18n.ts`: language types, default language, and shared UI copy
- `frontend/src/TimelineCard.tsx`: post and repost cards
- `frontend/src/archive.ts`: archive/date formatting and route helpers
- `frontend/src/api.ts`: API client and types
- `frontend/src/settings.ts`: browser-local settings and language persistence

### Backend

- `backend/app/api/posts.py`: timeline and search APIs
- `backend/app/api/navigation.py`: Friends and Hashtags aggregation
- `backend/app/api/analytics.py`: activity analytics
- `backend/app/api/presenters.py`: database-model to public-schema conversion
- `backend/app/core/config.py`: backend configuration

### Fetcher

- `fetcher/app/bluesky_client.py`: Bluesky XRPC client and re-authentication
- `fetcher/app/sync.py`: synchronization, owner-media eligibility, and reconciliation
- `fetcher/app/repository.py`: database updates
- `fetcher/app/media_downloader.py`: size-limited file storage
- `fetcher/app/config.py`: fetcher configuration

### Shared

- `shared/archive/bluesky_embed.py`: normalization of embeds, hashtags, labels, and direct media
- `shared/archive/db/models.py`: database models shared by backend and fetcher

## 6. Security boundaries

- Services receive only explicitly listed environment variables, not the complete `.env`.
- The backend and fetcher use separate database roles; neither receives DDL privileges.
- The backend is read-only except for the `sync_states` columns needed to request a manual sync.
- Only the fetcher can write to `media/`.
- Application services run as non-root UID/GID 3006.
- Application and nginx containers use read-only root filesystems, drop all capabilities, and enable `no-new-privileges`.
- Nginx access logs omit query strings and Referer headers.
- The HTTP interface has no built-in authentication and must not be exposed directly to the Internet.

## 7. Dependencies and tests

The backend and fetcher share the root non-package `pyproject.toml` and `uv.lock`. Runtime dependency groups are `backend` and `fetcher`; development uses `dev`. Production images perform a locked sync for only the required group in a builder stage and copy only `.venv` into the runtime stage.

Both applications use `app` as their top-level package name, so their pytest suites must run in separate processes.

~~~powershell
$env:PYTHONPATH='shared;backend'
uv run --locked pytest backend/tests -q

$env:PYTHONPATH='shared;fetcher'
uv run --locked pytest fetcher/tests -q
~~~

Media-policy tests must establish at least these invariants:

- Owner media is not downloaded by default.
- Direct owner attachments are stored when enabled.
- Media created by a different DID is not downloaded when enabled.
- Repost-source media is not downloaded even when the source view is complete.

The frontend production build includes TypeScript checking. Localization verification must cover the English default, switching to Japanese, persistence after reload, and document-language updates.

## 8. Post-deployment verification

| Target | Acceptance condition |
|---|---|
| Git | Intended commit and clean worktree |
| Compose | `docker compose config` succeeds |
| One-shot services | `db-migrate` and `db-grants` exit with code 0 |
| Long-running services | `postgres` and `backend` are healthy; `fetcher`, `frontend`, and `nginx` are running |
| HTTP | `/`, `/api/health`, `/api/calendar`, and `/api/timeline?limit=1` succeed |
| Localization | English is shown by default; switching to Japanese persists after reload |
| Media disabled | No real files appear under `media/images`, `media/videos`, or `media/captions` after sync |
| Media enabled | Only directly attached owner media is stored; repost-source media does not increase |

Never use `docker compose down -v` for a routine update. It deletes the PostgreSQL volume.

## 9. Development and licensing boundary

The project direction and requirements are specified by the maintainer, HAYASHI Tsukasa. OpenAI Codex creates and modifies the source code, tests, and documentation in this repository. AI-generated work is not represented as work produced solely by a human.

Original source code and documentation in the repository are provided under the MIT License to the extent the relevant rights apply. The copyright notice is `Copyright (c) 2026 HAYASHI Tsukasa`. OpenAI and OpenAI Codex are not identified as the copyright holder or maintainer.

The repository's MIT License does not cover:

- Python and Node.js dependencies or their transitive dependencies
- Docker base images and distributed artifacts
- Bluesky APIs, AT Protocol implementations, or external services
- Retrieved posts, actor data, raw JSON, images, videos, or captions

Those remain subject to their respective licenses, terms, and rights holders. Third-party license notices must not be removed or replaced by this repository's MIT License.
