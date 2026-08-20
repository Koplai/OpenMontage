#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

cleanup() {
  if [[ -f "index.html.composition-backup" ]]; then
    mv "index.html.composition-backup" "index.html"
  fi
  if [[ -f "index.motion.json.composition-backup" ]]; then
    mv "index.motion.json.composition-backup" "index.motion.json"
  fi
  for backup in compositions/*.qa-backup; do
    [[ -e "$backup" ]] || continue
    mv "$backup" "${backup%.qa-backup}"
  done
}
trap cleanup EXIT

FILES=(
  "index.html"
  "compositions/end-screen.html"
  "compositions/lower-third.html"
  "compositions/callout.html"
  "compositions/chapter-card.html"
)

check_file() {
  local file="$1"
  echo "Checking ${file}"
  if [[ "$file" == "index.html" ]]; then
    npx --yes hyperframes@0.8.4 check . --samples 15 --at-transitions --strict
    return
  fi

  local motion="${file%.html}.motion.json"
  cp "index.html" "index.html.composition-backup"
  cp "index.motion.json" "index.motion.json.composition-backup"
  cp "$file" "index.html"
  cp "$motion" "index.motion.json"
  set +e
  npx --yes hyperframes@0.8.4 check . --samples 15 --at-transitions --strict
  local status=$?
  set -e
  mv "index.html.composition-backup" "index.html"
  mv "index.motion.json.composition-backup" "index.motion.json"
  return "$status"
}

restore_file() {
  local file="$1"
  local backup="$2"
  if [[ -f "$backup" ]]; then
    cp "$backup" "$file"
    rm "$backup"
  fi
}

for file in "${FILES[@]}"; do
  check_file "$file"

  backup="${file}.qa-backup"
  cp "$file" "$backup"
  perl -0pi -e 's/"default": "es"/"default": "en"/' "$file"
  check_file "$file"
  restore_file "$file" "$backup"
done

for chapter in governance security roi; do
  file="compositions/chapter-card.html"
  backup="${file}.qa-backup"
  cp "$file" "$backup"
  perl -0pi -e "s/\"default\": \"architecture\"/\"default\": \"${chapter}\"/" "$file"
  check_file "$file"
  perl -0pi -e 's/"default": "es"/"default": "en"/' "$file"
  check_file "$file"
  restore_file "$file" "$backup"
done

echo "All bilingual motion compositions passed strict transition-aware QA."
