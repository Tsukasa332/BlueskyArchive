FROM node:22.23.5-bookworm-slim AS build

WORKDIR /app
RUN npm install --global pnpm@11.28.10
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm run build

FROM ghcr.io/nginx/nginx-unprivileged:1.30.7-trixie
USER root
# Fail the build if the Debian Brotli security update is unavailable.
RUN apt-get update \
    && apt-get install -y --no-install-recommends --only-upgrade libbrotli1 \
    && dpkg --compare-versions "$(dpkg-query -W -f='${Version}' libbrotli1)" ge '1.1.0-2+deb13u1' \
    && rm -rf /var/lib/apt/lists/*
USER 101
COPY --from=build --chown=101:101 /app/dist /usr/share/nginx/html
EXPOSE 8080
