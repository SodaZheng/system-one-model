#!/bin/sh
set -eu
cd "$(dirname "$0")"
sha256sum --check SHA256SUMS
if [ ! -f .env ]; then
  (umask 077; python3 -c 'import secrets; print("API_KEY=" + secrets.token_urlsafe(32)); print("PORT=8080")' > .env)
fi
docker load -i one-system-model-1.2-amd64.tar
docker compose up -d
