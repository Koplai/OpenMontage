#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
CAMERA_SETTINGS="$HOME/Library/Application Support/Elgato/Camera Hub/AppSettings.json"
OBS_PROFILE="$HOME/Library/Application Support/obs-studio/basic/profiles/Untitled/basic.ini"
OBS_SCENES="$HOME/Library/Application Support/obs-studio/basic/scenes/Untitled.json"
STREAMDECK_PROFILE="$HOME/Library/Application Support/com.elgato.StreamDeck/ProfilesV3/0EF92394-42C1-4574-A812-7BC966E23BFA.sdProfile"
BACKUP_ROOT="$HOME/Library/Application Support/JPMarquez Recording/Backups"
BACKUP_DIR="$BACKUP_ROOT/$(date +%Y%m%d-%H%M%S)"

for path in "$CAMERA_SETTINGS" "$OBS_PROFILE" "$OBS_SCENES" "$STREAMDECK_PROFILE"; do
  if [[ ! -e "$path" ]]; then
    echo "Required configuration not found: $path" >&2
    exit 1
  fi
done

mkdir -p "$BACKUP_DIR"

osascript -e 'tell application id "com.elgato.CameraHub" to quit' >/dev/null 2>&1 || true
osascript -e 'tell application id "com.obsproject.obs-studio" to quit' >/dev/null 2>&1 || true
osascript -e 'tell application id "com.elgato.StreamDeck" to quit' >/dev/null 2>&1 || true
sleep 4

for process_name in "Camera Hub" "OBS" "Stream Deck"; do
  if pgrep -x "$process_name" >/dev/null; then
    echo "$process_name is still running. Quit it normally and run setup-recording.sh again." >&2
    exit 1
  fi
done

ditto "$CAMERA_SETTINGS" "$BACKUP_DIR/CameraHub-AppSettings.json"
ditto "$OBS_PROFILE" "$BACKUP_DIR/OBS-basic.ini"
ditto "$OBS_SCENES" "$BACKUP_DIR/OBS-Untitled.json"
ditto "$STREAMDECK_PROFILE" "$BACKUP_DIR/StreamDeck-profile.sdProfile"

node "$SCRIPT_DIR/configure-recording.mjs" \
  --camera-settings "$CAMERA_SETTINGS" \
  --obs-profile "$OBS_PROFILE" \
  --obs-scenes "$OBS_SCENES" \
  --streamdeck-profile "$STREAMDECK_PROFILE" \
  --repo-root "$REPO_ROOT"

open -a "/Applications/Elgato Camera Hub.app"
open -a "/Applications/OBS.app"
open -a "/Applications/Elgato Stream Deck.app"
open "$SCRIPT_DIR/record.html"

echo
echo "VID-001 recording controls installed directly on all 15 Stream Deck keys."
echo "Backup: $BACKUP_DIR"
echo "If Stream Deck cannot control Camera Hub, enable Camera Hub and Stream Deck"
echo "in System Settings > Privacy & Security > Accessibility."
