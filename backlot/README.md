# Backlot — the living storyboard

A read-only local board that shows a production happening: pipeline stages
lighting up, the script as a screenplay page, the scene plan as a filmstrip
that fills in as assets generate, decisions, spend, and activity — all
derived from what the pipeline already writes to `projects/<id>/`.

```bash
python -m backlot open <project-id>   # start server if needed + open browser
python -m backlot open                # library view (all projects)
python -m backlot serve --port 4750   # run the server in the foreground
```

## How it stays live

No agent involvement. A `watchfiles` watcher on `projects/` publishes change
notifications over SSE; the browser refetches board state. State sources:

| Board element | Disk source |
|---|---|
| identity / rail order | `project.json` + `pipeline_defs/<type>.yaml` |
| stage states, gates, versions | `checkpoint_<stage>.json` + `history/` |
| script card / modal | `artifacts/script.json` |
| filmstrip cards | `scene_plan × script × asset_manifest` join |
| generating shimmer, activity | `events.jsonl` (written by `BaseTool` instrumentation) |
| cost meter | checkpoint `cost_snapshot` |
| renders | `renders/*.mp4` (+ root-level mp4 heuristic) |

Projects without checkpoints degrade gracefully to a "what the watcher
found" view — media, snapshots, renders.

### Reliability and damaged state

Backlot validates the nested shapes it consumes, **without rewriting or
approving production artifacts**. Bad JSON, checkpoint metadata/artifact
containers, non-finite numbers, and invalid scene/section times produce a
visible **DAMAGED PROJECT STATE** notice. Readable siblings and review media
remain available. The state API and library summaries include an additive
`diagnostics: [{scope, message}]` field; scopes identify the file and nested
field. Malformed fields are replaced with empty containers or `null`, and
invalid object-array entries are omitted from the board projection. The
artifact drawer displays that projection, not a byte-for-byte forensic copy.
This is defensive display validation, not a replacement for production schemas.

The watcher retries when the projects root is absent or removed. SSE `hello`
(including reconnect) and 15-second heartbeats trigger reconciliation as well
as change events, so missed notifications and elapsed LIVE/IDLE/STALLED status
recover without manual reload. Library summaries expire after 15 seconds and
are capped at 128 entries; deleted projects are evicted. Thumbnail generations
are pruned to 256 JPEGs / 64 MiB after generation, with failed temporary files
cleaned up. These are cache limits, not project storage quotas.

Refresh captures video/audio position, pause/play state, volume, mute, and
playback rate before replacing the board. The selected render is matched by
path when a newer version arrives. Recreated media may briefly reload; browser
autoplay policy can still require a click to resume. `?static=1` intentionally
disables reconciliation. A missing project (404) is distinguished from a
temporarily unavailable state/API; a failed live request leaves the last
readable board visible with an error notice.

### Trusted local boundary

The CLI remains **127.0.0.1-only**: it has no `--host`/public-bind option.
`/api/health` returns `ok`, `app: "backlot"`, `api_version: 1`, and a
`workspace_id` (SHA-256 of the resolved projects-root path). `backlot open`
accepts only this app/version/workspace combination, not an arbitrary HTTP 200
on the port. A conflicting workspace/app requires a different `BACKLOT_PORT`.
The identity is for discovery, not authentication.

`OPENMONTAGE_PROJECTS_DIR` selects the trusted workspace boundary (the root
itself may be a symlink). Project links resolving outside that root are omitted
from the library and return 403 through project/media APIs. Inside a selected
project, JSON references, canonical files, events, discovered media, and
media/thumb routes must resolve inside that project's root. In-workspace
project aliases and in-project file links still work; escaping or looping
links do not. Ordinary media and byte Range responses remain supported.

Authored HTML/SVG delivered by **either** `/media` or `/thumb` receives a CSP
`sandbox allow-scripts` **without** `allow-same-origin`, plus `nosniff` and
`no-referrer`. This gives executable documents an opaque browser origin even
when opened directly, rather than access to the board's storage/API. Inline
scripts/styles and local display resources remain possible; fetch/XHR,
embedded frames, forms, and external resources are restricted. Compositions
requiring CDN scripts, modules/CORS, or API access may need their dedicated
authoring/preview runtime; the board does not relax the sandbox for them.

This is **not** a hostile-content hosting service: no multi-user auth, Host
authorization, process isolation, or guaranteed egress isolation is provided.
Do not expose the ASGI app publicly or import untrusted projects. Resolved-path
checks are not race-proof against another process deliberately swapping
symlinks during a read; untrusted concurrent writers require OS-level isolation
and a separately hosted media service.

### Tests and synthetic screenshots

```bash
python -m pytest tests/backlot -q
```

HTTP tests use the actual ASGI app, including Range and SSE delivery; the
JavaScript regressions execute in Node without npm packages. Browser tests
require Python Playwright and an installed Chromium. They use temporary
projects/cache directories and a reserved ephemeral loopback socket (POSIX),
block external HTTP/WebSocket requests and service workers, and use only
synthetic media. Set `BACKLOT_TEST_CHROMIUM=/absolute/path/to/chromium` to use an
already cached executable. Missing browser dependencies are not auto-installed.

Importing `scripts.backlot_screenshot_stage` no longer changes environment
variables or deletes a staging directory. `build_stage(stage_dir=...)` requires
a new directory; its synthetic checkpoints are independent of production
writers. The explicit screenshot CLI still resets only its dedicated
`.backlot/screenshot-stage` area and writes README screenshots as before.
Do not use that CLI as a test fixture or run it against production data.

**Replay**: a completed run can be scrubbed end-to-end (▶ REPLAY RUN on the
board) — reconstructed from checkpoint history and event timestamps.

Try it without a real production:

```bash
python scripts/backlot_simulate_run.py          # live demo run (~1 min)
python -m backlot open backlot-demo-run
```

Design doc: `internal/design/LIVING_STORYBOARD.md`.
