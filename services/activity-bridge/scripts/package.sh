#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ZIP_NAME="discord-activity-stream-control.zip"

cd "$ROOT_DIR"
rm -f "../$ZIP_NAME"
zip -r "../$ZIP_NAME" . \
  -x "node_modules/*" \
  -x "client/dist/*" \
  -x "server/dist/*" \
  -x "shared/dist/*" \
  -x ".env" \
  -x "*.log"

echo "Created ../$ZIP_NAME"
