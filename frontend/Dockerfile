FROM node:22.22.3-bookworm-slim AS build

WORKDIR /app
RUN npm install --global pnpm@11.7.0
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm run build

FROM nginxinc/nginx-unprivileged:1.30.4-trixie
COPY --from=build --chown=101:101 /app/dist /usr/share/nginx/html
EXPOSE 8080
