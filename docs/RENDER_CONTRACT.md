# Render contract

This contract covers trusted, private, single-user rendering. It does not
certify arbitrary authored JavaScript/HTML as safe, approve generation costs,
or replace human review of creative quality.

## Runtime selection

`video_compose(operation="render")` requires `edit_decisions.render_runtime`.
An explicit `remotion`, `hyperframes`, or `ffmpeg` choice is binding. Missing
dependencies and runtime failures return a blocker, never a substitute engine.
The low-level `compose` and `remotion_render` operations also reject a
contradictory locked runtime. Results distinguish `requested_runtime` from
`executed_runtime`.

Remotion must already have its composer dependencies installed. Its CLI uses
`npx --no-install`; no automatic package installation is permitted.
HyperFrames uses **0.8.40**, defined by
`tools.video.hyperframes_compose.HYPERFRAMES_VERSION`. Discovery reads local
package metadata and the installed CLI entry, plus the local Node version;
it never runs npm, npx, doctor, installation, or browser setup. An absent or
different version is unavailable. Execution launches that exact installed
entry with Node, not an unversioned package-manager command.

Install/update and `doctor` are explicit operator actions, not status checks.
Runtime availability means “installed prerequisites found,” not “browser
rendering has been certified.” Authored compositions may reference remote
resources; actual browser execution can fetch those resources.

## Timeline: source time is not composition time

Canonical cuts retain their original source coordinates:

```json
{
  "id": "clip-a",
  "source": "assets/clip.mp4",
  "in_seconds": 2,
  "out_seconds": 6,
  "speed": 2,
  "timeline_start_seconds": 0,
  "timeline_duration_seconds": 2
}
```

- `in_seconds`/`out_seconds`: inclusive/exclusive source trim.
- `speed`: positive playback multiplier, default `1`.
- `timeline_duration_seconds`: `(out_seconds - in_seconds) / speed`.
  This optional field is an assertion; disagreement is an error.
- `timeline_start_seconds`: position in the composition. Omitted cuts append
  sequentially after preceding cuts, not at their source trim time.
- Negative/nonfinite values and empty/reversed trims fail instead of being
  skipped. Rendered visual duration must agree with the canonical cut timeline
  within 100 ms (frame/container rounding allowance).

Python adapters share `lib/render_timeline.py`; Remotion's pure TypeScript
adapter is tested against the same example. Explainer uses explicit sequence
positions, trimmed media playback, and speed without the former extra second
of trailing padding. Cinematic reuses its existing cut-to-scene adapter,
including title-background playback speed.

FFmpeg concat and templated HyperFrames currently require **sequential primary
cuts**. Gaps, overlaps, and nonprimary cut layers are explicit blockers there,
not flattened away. Explainer/cinematic can use explicit positions. Other
compositing requirements should use an authored composition.

HyperFrames 0.8.40 exposes `data-start` and `data-media-start`, but no documented
playback-rate attribute. Non-unit-speed video is locally trimmed/retimed with
FFmpeg before rendering. The canonical trim/speed remains in the decisions;
the materialized clip is played from media offset zero. Video audio is emitted
as a separate timed audio element, as required by HyperFrames.

### Compatibility

Canonical `edit_decisions` always uses the contract above. Existing raw
`composition_data` for Explainer retains its historical timeline interpretation
through `timeline_mode: "legacy"`: `in_seconds`/`out_seconds` position the cut,
and `source_in_seconds` selects the source offset. Explicit normalized timeline
props use `timeline_mode: "sequential"`. New callers should use canonical cuts.

Presenter canonical routing adapts **one video cut** into TalkingHead's
`videoSrc`, source trims, playback rate, and duration. Multiple cuts require
explicit pre-composition and are blocked rather than producing a blank
300-second presentation. Existing raw `videoSrc` callers retain support;
metadata derives their real media duration.

## Approved audio and subtitles

- Explicit audio/subtitle paths must exist before visual rendering starts.
  Subtitle asset IDs are resolved through the supplied asset manifest.
- `audio_path` is the approved **complete mix** replacing source audio.
  FFmpeg, Remotion, and HyperFrames reuse the padded mux: short audio is padded
  with silence and never truncates visuals.
- `subtitle_path` is forwarded and burned after Remotion/HyperFrames rendering;
  FFmpeg composition burns it during its finishing pass. A build without the
  `subtitles`/libass filter blocks **before** visual rendering. Arbitrary path
  punctuation is handled through a safe staged subtitle basename.
- Canonical string `subtitles.style` is a display-mode label, not a dictionary.
  Adjacent typography fields and legacy dictionary styles remain supported.
  Word-level/karaoke string styles require approved timed ASS/SSA or explicit
  Remotion caption props; sentence SRT with such a style is an explicit blocker,
  not a fabricated word-timing conversion.
- Disabling subtitle burn while supplying approved subtitles is an error.
  An existing source subtitle file alone is not evidence of subtitles in the
  output. `has_subtitles` records a completed burn or embedded caption render;
  it is not a claim that OCR or timing/coverage verification was performed.
- Canonical narration/music/SFX references require an approved mixed
  `audio_path` for FFmpeg/Remotion and arbitrary authored workspaces.
  Templated HyperFrames supports narration segments and constant-volume music;
  SFX, ducking, and fades require a premix rather than being ignored.
  Explicit music volume `0` remains muted.

## Assets, isolation, and acceptance

HyperFrames stages media by SHA-256, not basename or file size. Missing
required references block scaffolding. Only explicit `draft: true` permits
labeled missing-visual placeholders; the missing references remain in the
result, and draft output is never an accepted high-level deliverable.
Unresolved narration/music still blocks.

Each invocation gets its own output work directory, props, FFmpeg segments,
and staging area. Templated HyperFrames gets a unique workspace; authored
HyperFrames is checked/rendered in an isolated copy without rewriting the
original entry. Static local HTML/CSS references are checked before the CLI;
computed JavaScript references remain the runtime check's responsibility.
Review frame directories are unique and retained for inspection.

Final output publication uses a same-filesystem atomic rename only after the
new candidate exists and passes probe plus full decode through
`lib.delivery_validation.validate_media`. An old output is never evidence that
the current renderer succeeded; failed attempts leave the old destination
untouched. Use distinct destination paths for concurrent jobs: if callers
intentionally share a destination, the last successful atomic publication wins.
Downstream digest validation detects a subsequently replaced deliverable.

Low-level file-production success is **not** final delivery acceptance.
High-level render requires `final_review.status == "pass"`; both `revise` and
`fail` produce `success=False` and `deliverable_accepted=False`. Technical
diagnostics may still be available, but must not be presented as final.
Reviews bind to:

- `output_path`
- `output_sha256`
- `output_size_bytes`
- timezone-aware `reviewed_at`

Checkpoint/export enforcement consumes these fields through the shared
delivery validator. Renderer tests do not replace that downstream boundary.
R13's replacement-bundle behavior belongs to export, not this renderer.

## Verification and limits

`tests/tools/test_render_hardening.py` exercises runtime locking, trim/speed,
source-frame identity, short audio, apostrophe paths, draft blocking,
collision-resistant staging, presenter adaptation, concurrent props,
fresh-output rejection, passive runtime detection, byte-valued timeout
diagnostics, and review identity. FFmpeg fixtures are synthetic and zero-key.
The TypeScript adapter is executed with installed TypeScript; composer
`tsc --noEmit` is also required.

No browser download, dependency installation, model invocation, or real
content generation is required by these tests. Full Remotion/HyperFrames
browser rendering remains an explicit environment acceptance check. The
current local FFmpeg build lacks libass: tests verify its explicit subtitle
blocker, not a successful burn on that build. Burn success still needs a
libass-enabled environment; no installation was performed here.
