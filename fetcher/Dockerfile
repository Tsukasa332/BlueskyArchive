FROM ghcr.io/astral-sh/uv:0.12.2 AS uv

FROM python:3.12-slim-bookworm AS builder

ENV UV_LINK_MODE=copy

WORKDIR /app

COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-default-groups --only-group fetcher

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/shared \
    PATH=/app/.venv/bin:$PATH

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv

RUN groupadd --gid 3006 blueskyarchive \
    && useradd --uid 3006 --gid 3006 --no-create-home --home-dir /nonexistent \
        --shell /usr/sbin/nologin --no-log-init blueskyarchive

COPY --chown=3006:3006 shared /app/shared
COPY --chown=3006:3006 fetcher /app/fetcher

WORKDIR /app/fetcher
USER blueskyarchive:blueskyarchive
CMD ["python", "-m", "app.main"]
