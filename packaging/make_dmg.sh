#!/usr/bin/env bash
# Build the macOS installer disk image.
#
#   ./packaging/make_dmg.sh [output.dmg]
#
# Expects packaging/dist/<APP_NAME>.app to exist (run pyinstaller first).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="${APP_NAME:-Filery}"
APP="$HERE/dist/$APP_NAME.app"
OUT="${1:-$HERE/dist/$APP_NAME.dmg}"

[ -d "$APP" ] || { echo "error: no app bundle at $APP - run pyinstaller first" >&2; exit 1; }

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

cp -R "$APP" "$STAGE/"
# the drag-to-install gesture everyone expects
ln -s /Applications "$STAGE/Applications"

rm -f "$OUT"
hdiutil create \
  -volname "$APP_NAME" \
  -srcfolder "$STAGE" \
  -ov -format UDZO \
  -imagekey zlib-level=9 \
  "$OUT" >/dev/null

echo "$OUT ($(du -h "$OUT" | cut -f1))"
