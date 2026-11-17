#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 scripts/init_env.py
# Apple container's --tmpfs syntax differs from Docker; use its normal writable root.
container run -d --name one-system-model --arch amd64 --cpus 8 --memory 14G \
  --env-file .env -p 127.0.0.1:8080:8080 one-system-model:1.2
