#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p renders

render() {
  local composition="$1"
  local output="$2"
  local format="$3"
  local variables="$4"

  echo "Rendering ${output}"
  npx --yes hyperframes@0.8.4 render \
    --composition "$composition" \
    --output "renders/${output}" \
    --format "$format" \
    --fps 30 \
    --variables "$variables" \
    --strict-variables \
    --strict
}

for language in es en; do
  render "." "jp-micro-intro-${language}.mp4" "mp4" "{\"language\":\"${language}\"}"
  render "compositions/end-screen.html" "jp-end-screen-${language}.mp4" "mp4" "{\"language\":\"${language}\"}"
  render "compositions/lower-third.html" "jp-lower-third-${language}.webm" "webm" "{\"language\":\"${language}\"}"
  render "compositions/callout.html" "jp-evidence-callout-${language}.webm" "webm" "{\"language\":\"${language}\"}"

  for chapter in architecture governance security roi; do
    render \
      "compositions/chapter-card.html" \
      "jp-chapter-${chapter}-${language}.mp4" \
      "mp4" \
      "{\"language\":\"${language}\",\"chapter\":\"${chapter}\"}"
  done
done

echo "Rendered all bilingual motion assets."
