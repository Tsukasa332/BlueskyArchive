# BlueskyArchive

English | [日本語](README_JP.md)

## Statement from the maintainer

> This is the only statement in this repository whose substance was supplied directly by the maintainer; wording normalization and the English translation were done by Codex. The maintainer provides only the design and instructions. Codex performs all coding, testing, and documentation work. The application has been verified on Debian GNU/Linux 12 (bookworm) with Docker Engine 29.7.2. It is expected to work with Docker Desktop on Windows 11, but that environment has not been verified. Feature requests are not accepted. Fork the repository and make any additional changes in your own fork.

A personal archive that stores your Bluesky posts and reposts in PostgreSQL and provides a searchable, Twilog-style browsing interface.

This public edition does not include the image viewer for the wider Bluesky network or the public block-list feature. Local storage of images, videos, and video captions is disabled by default. When enabled, it stores only media directly attached to posts created by the archived account; it never stores media from reposted or quoted posts created by other people.

The web interface defaults to English. Use the language button in the header, or the display-language option under Settings, to switch between English and Japanese. The selection is stored only in the current browser.

## Development disclosure

The project direction and requirements are specified by the maintainer, HAYASHI Tsukasa. OpenAI Codex creates and modifies the source code, tests, and documentation in this repository. AI-generated work is not represented as work produced solely by a human.

OpenAI and OpenAI Codex are not identified as the copyright holder or maintainer. See the repository's [LICENSE](LICENSE) for copyright and licensing terms.

## Features

- Periodic retrieval of your posts, replies, quotes, and reposts
- Filtering and search by day, month, full text, reply recipient, and hashtag
- Timeline ordering by newest first, chronological time within each day, or oldest first
- Interpretation of `images`, `gallery`, `video`, `external`, `record`, and `recordWithMedia` embeds
- Recent, Archives, Friends, and Hashtags sidebar sections
- Post-type and day/time analytics
- Reconciliation of deleted posts and reposts
- Optional storage of the account owner's media, with per-file, total-size, and free-space limits
- English and Japanese user interfaces with a browser-local language preference

## Media storage policy

The `SAVE_OWN_MEDIA` value in `.env` controls local media storage.

| Value | Behavior |
|---|---|
| `false` | Does not store images, videos, or video captions locally. This is the default. |
| `true` | Stores only directly attached media and video captions from posts created by the authenticated archive account. |

The following are never stored locally, even when `SAVE_OWN_MEDIA=true`:

- Images, videos, or captions from the source posts of reposts
- Images, videos, or captions from quoted posts
- Media from posts created by any other account

Post and repost text, actor data, embed metadata, and raw AT Protocol JSON are stored in PostgreSQL separately from media files. A raw repost view may contain Bluesky CDN URLs, but the referenced image or video files are not downloaded.

Changing the setting from `true` to `false` does not delete files or media records that already exist. Audit existing data when migrating an older environment to this public edition. Starting with an empty database and empty `media/` directory is safest for a new installation.

## Architecture

- `nginx`: HTTP entry point and router for the frontend, backend API, and owner media
- `frontend`: React 19, TypeScript, and Vite interface
- `backend`: FastAPI REST API for PostgreSQL search and aggregation
- `fetcher`: Retrieves posts, reposts, and actors from Bluesky; stores owner media only when enabled
- `postgres`: Stores archive data, search indexes, sync state, and run history
- `db-migrate`: One-shot Alembic migration service
- `db-grants`: One-shot service that applies and verifies backend/fetcher database privileges

The frontend and database use separate Docker networks. Only the backend joins both. The backend, fetcher, and both nginx containers use read-only root filesystems, drop all capabilities, and enable `no-new-privileges`. The backend and fetcher run as non-root UID/GID 3006.

See [docs/architecture.md](docs/architecture.md) for details.

## Requirements

- Docker Engine and Docker Compose v2
- The Bluesky account to archive
- A Bluesky App Password
- For development only: Python 3.12, uv, Node.js, and pnpm 11.7.0

## First deployment

~~~bash
git clone <repository-url> BlueskyArchive
cd BlueskyArchive
cp .env.example .env
chmod 600 .env
~~~

At minimum, change these values in `.env`:

- `BLSKY_IDENTIFIER`
- `BLSKY_APP_PASSWORD`
- `POSTGRES_PASSWORD`
- `BACKEND_DB_PASSWORD`
- `FETCHER_DB_PASSWORD`

Use a different, sufficiently long random value for each database password. Set `SAVE_OWN_MEDIA=true` only if local owner-media storage is required.

On Linux, give the fetcher ownership of `media/`:

~~~bash
sudo chown -R 3006:3006 media
docker compose up -d --build
docker compose ps -a
docker compose logs --tail=100 db-migrate db-grants backend fetcher frontend nginx
~~~

Example health checks:

~~~bash
curl -fsS http://127.0.0.1:8080/ -o /dev/null
curl -fsS http://127.0.0.1:8080/api/health
curl -fsS http://127.0.0.1:8080/api/calendar -o /dev/null
curl -fsS 'http://127.0.0.1:8080/api/timeline?limit=1' -o /dev/null
~~~

## Environment variables

| Variable | Default and purpose |
|---|---|
| `POSTGRES_DB` | `bluesky_archive`: PostgreSQL database name |
| `POSTGRES_USER` | `bluesky`: administrative migration role |
| `POSTGRES_PASSWORD` | Administrative role password; always change it |
| `BACKEND_DB_USER` | `bluesky_backend`: backend role |
| `BACKEND_DB_PASSWORD` | Backend role password; always change it |
| `FETCHER_DB_USER` | `bluesky_fetcher`: fetcher role |
| `FETCHER_DB_PASSWORD` | Fetcher role password; always change it |
| `BLSKY_IDENTIFIER` | Bluesky account to archive |
| `BLSKY_APP_PASSWORD` | Bluesky App Password used by the fetcher |
| `SAVE_OWN_MEDIA` | `false`; stores directly attached owner media only when `true` |
| `APP_TIMEZONE` | `Asia/Tokyo`; date boundaries and calendar aggregation |
| `MEDIA_MIN_FREE_BYTES` | `5368709120`; preserve 5 GiB of free space after a download |
| `MEDIA_MAX_FILE_BYTES` | `157286400`; 150 MiB per-file limit |
| `MEDIA_MAX_TOTAL_BYTES` | `53687091200`; 50 GiB total media limit |
| `MEDIA_TOTAL_SCAN_INTERVAL_SECONDS` | `300`; interval for recalculating total media size |
| `FETCH_INTERVAL_SECONDS` | `900`; normal sync interval |
| `FETCH_PAGE_LIMIT` | `100`; records per Bluesky API page |
| `FULL_RECONCILE_INTERVAL_SECONDS` | `86400`; full CID/deletion reconciliation interval |
| `ERROR_BACKOFF_SECONDS` | `60`; retry delay after a failed sync |
| `HTTP_PORT` | `8080`; host HTTP port |

`MEDIA_ROOT` is fixed to `/app/media` inside the containers. If a download would exceed the per-file limit, total-size limit, or minimum-free-space requirement, the media is not stored and the sync fails.

## Security notes

- `.env` contains the Bluesky App Password and database passwords. Never commit it.
- Compose publishes `0.0.0.0:8080` by default. The application has no authentication. Do not expose it directly to the Internet; restrict access with a firewall, VPN, or authenticated reverse proxy.
- Post text, raw JSON, database dumps, and owner media are personal data. Do not add them to a public repository.
- FastAPI's `/docs`, `/redoc`, and `/openapi.json` endpoints are disabled.
- `docker compose down -v` deletes the PostgreSQL volume. Do not use it for routine updates.

## Development

The backend and fetcher share the root non-package uv project and `uv.lock`. Both top-level packages are named `app`, so collect their tests in separate pytest processes.

~~~powershell
uv sync --locked

$env:PYTHONPATH='shared;backend'
uv run --locked pytest backend/tests -q

$env:PYTHONPATH='shared;fetcher'
uv run --locked pytest fetcher/tests -q

Set-Location frontend
pnpm install --frozen-lockfile
pnpm run build
~~~

After changes, also run `git diff --check` and `docker compose config`. Use only `uv.lock` and `frontend/pnpm-lock.yaml` for dependency resolution; do not add `requirements.txt` or `package-lock.json`.

## API

- `GET /api/posts`
- `GET /api/reposts`
- `GET /api/timeline`
- `GET /api/timeline/search?tag=TAG`
- `GET /api/timeline/replies?reply_to=DID`
- `GET /api/navigation?limit=20`
- `GET /api/analytics?period=all|year|month|week`
- `GET /api/posts/{id}`
- `GET /api/calendar`
- `GET /api/search`
- `GET /api/health`
- `GET /api/sync`
- `POST /api/sync`

## Repairing repost source views

To refresh only the source-post view for a stored repost, provide either the repost URI or the source-post URI. The public edition never stores source-post images or videos.

~~~bash
docker compose exec fetcher python -m app.repair_reposts \
  at://did:plc:example/app.bsky.feed.post/example
~~~

## Backup

A complete restoration requires:

- The PostgreSQL volume or a database dump
- `media/` when operating with `SAVE_OWN_MEDIA=true`
- `.env`
- The Git commit used by the deployment

Backups also contain post content, credentials, and possibly owner media. Do not commit or publish them.

## Files that must not be committed

- `.env`, `.venv/`, `.pnpm-store/`, `node_modules/`
- Python and pytest caches, `frontend/dist/`
- Real files under `media/`
- PostgreSQL data, dumps, backups, and `outputs/`
- Passwords, App Passwords, and SSH private keys

Only `media/images/.gitkeep`, `media/videos/.gitkeep`, and `media/captions/.gitkeep` are tracked to preserve empty directories.

## License

Original source code and documentation in this repository are provided under the MIT License to the extent the relevant rights apply.

Copyright (c) 2026 HAYASHI Tsukasa

The repository's MIT License does not cover dependency libraries, container images, external services, or post/actor/raw JSON/media data retrieved from Bluesky. Those remain subject to their respective rights holders and terms. See [LICENSE](LICENSE) for the full text.
