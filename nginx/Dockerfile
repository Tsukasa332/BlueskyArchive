FROM nginxinc/nginx-unprivileged:1.30.6-trixie

USER root
# Fail the build if the Debian Brotli security update is unavailable.
RUN apt-get update \
    && apt-get install -y --no-install-recommends --only-upgrade libbrotli1 \
    && dpkg --compare-versions "$(dpkg-query -W -f='${Version}' libbrotli1)" ge '1.1.0-2+deb13u1' \
    && rm -rf /var/lib/apt/lists/*
USER 101
