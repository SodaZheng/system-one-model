#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
destination=${1:-artifacts/export}
mkdir -p "$destination"
container image save --platform linux/amd64 -o "$destination/image.oci.tar" one-system-model:1.2
python3 scripts/oci_to_docker.py "$destination/image.oci.tar" "$destination/one-system-model-1.2-amd64.tar" --tag one-system-model:1.2
cp compose.yaml "$destination/compose.yaml"
cp deploy/start.sh deploy/verify.py deploy/README.md artifacts/long-cases.json "$destination/"
cp docs/validation.md "$destination/validation.md"
(cd "$destination" && shasum -a 256 one-system-model-1.2-amd64.tar compose.yaml start.sh verify.py long-cases.json > SHA256SUMS)
