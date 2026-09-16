# Private production operations

OpenMontage is an agent-driven source workspace, not a public multi-tenant
service. The supported release route is a **source checkout with Python 3.12,
Node 22, and FFmpeg/ffprobe**. Keep Backlot on loopback. Do not expose authored
JavaScript, uploaded projects, or local tool execution to untrusted users.
Do not treat a successful test run as verification of a provider account,
commercial license, real creative quality, or an unattended deployment.

## Install reproducibly

```bash
make install-dev
npm --prefix remotion-composer ci
make lint
npm --prefix remotion-composer test
make test
make audit
```

`requirements.lock` and `requirements-dev.lock` pin transitive Python versions
and hashes. The development lock also provides the browser test and dependency
audit tools. `npm ci` consumes the committed npm lock; Remotion packages are
pinned together. `requirements-bootstrap.lock` pins the installer itself, so an
older Python venv's bundled pip is not silently retained. Python 3.12 is the interpreter used to generate and verify the
locks. Review changes to the source requirements and regenerate both locks
with `pip-compile --generate-hashes --allow-unsafe`; do not hand-edit hashes.
Run both runtime and development dependency scans after a refresh.

`make setup` installs the locked core and composer. It does not create `.env`,
install optional TTS/model packages, or fetch HyperFrames automatically.
Provider/model-specific environments remain explicit optional installations;
record their versions and model rights before production.

HyperFrames is pinned to 0.8.40. `make hyperframes-warm` explicitly installs that
version; `make hyperframes-doctor` is an explicit runtime check. Neither a new
latest tag nor a fallback renderer is an implicit substitute for an approved
runtime.

The wheel includes Python dependencies and package-local schemas/UI, but is
**not the standalone studio distribution**: pipeline instructions, project
workspaces, vendored skills, and renderer workspaces require the source tree.
Do not deploy only the wheel and infer it is equivalent to the checkout.

## Credentials and preflight

Supply credentials through a trusted process launcher or secret manager such
as OpenBao. Never put them in generated projects, exported bundles, Git, or
audit logs.

Keep production data outside disposable development worktrees. Before launching
the agent and Backlot, set an absolute, stable projects root in the trusted
environment, for example:

```bash
export OPENMONTAGE_PROJECTS_DIR="$HOME/Media/OpenMontage/projects"
```

Checkpoint APIs, event attribution, and Backlot share this setting. Do not put
it in a project `.env`. Use a stable working directory while paid requests are
pending: approvals also bind request path resolution and provider/tool identity.

Legacy `.env` support now uses `lib/env_policy.json` in both Python and the
vendored HeyGen JavaScript loader. Unknown keys, process-control settings,
endpoint overrides, and credential-file locations are refused with key-only
warnings. Existing nonblank process values win. Values are not interpolated.
Provider regions are restricted to safe slugs. If an endpoint or executable
override is intentional, set it in the trusted launch environment, not in a
project-supplied `.env`.

```bash
make preflight
```

This inventory checks declared prerequisite presence without calling provider
health methods or launching runtime probes. It distinguishes `configured`,
`missing`, and `unverified`; it never prints credential values. Discovery
imports trusted tool modules, so this is not a sandbox for third-party Python.
Failed optional imports are logged and included in the inventory rather than
silently hiding the missing module.

`make runtime-preflight` performs the separate runtime-capability check required
by the production pipeline. Configuration presence does not prove successful
authentication, quota, model access, or service health.

## Local media and browser qualification

```bash
make test-qa
```

Legacy diagnostics now run explicitly, in temporary output directories, with
bounded subprocess execution and nonzero failure status. They no longer execute
during pytest collection. To select only independent local checks:

```bash
.venv/bin/python scripts/run_local_qa.py \
  --script test_04_audio_mix.py \
  --script test_06_video_stitch.py \
  --script test_07_playbook_intelligence.py
```

The video composition diagnostic requires FFmpeg's `subtitles` filter for its
caption checks. Some Homebrew FFmpeg builds omit libass; a failed caption
diagnostic on such a build is a **missing delivery capability**, not permission
to omit captions. Provision a supported FFmpeg build or explicitly approve a
tested caption-capable renderer. The audit machine's FFmpeg lacked libass.

Backlot browser tests require Python Playwright plus its matching Chromium:

```bash
.venv/bin/python -m playwright install chromium
.venv/bin/python -m pytest tests/backlot/test_ui_bug_bash.py -q
```

Browser installation is an explicit provisioning step. CI installs Chromium and
system libraries before running the tests. These tests use synthetic fixtures;
they are not a review of real customer content.

## Back up and restore paused projects

Paid assets, approval records, and checkpoints are not reproducible merely
because `projects/` is ignored by Git. Keep an independently stored backup of
the whole production, not only its final MP4.

Stop project writers and checkpoint any `in_progress` stages before backup.
Backup holds the same local directory lock as checkpoint writers and refuses a
pending checkpoint journal; recover it through the checkpoint API first.
The archive command refuses active checkpoints, symlinks, common secret-file
names, special files, and oversized inputs. It stores hashes of the exact
archived bytes; this is integrity checking, not encryption or a guarantee that
arbitrary media/text contains no sensitive information.

```bash
.venv/bin/python -m lib.project_archive backup \
  projects/my-production /safe/local-backups/my-production.zip

.venv/bin/python -m lib.project_archive restore \
  /safe/local-backups/my-production.zip projects/my-production
```

The archive and restore destination must not already exist. Backup must be
outside the source project. Restore validates every file and hash before
publishing the restored directory; path traversal, symlinks, extra entries, and
tampered content fail without replacing an existing production. Restore keeps
the recorded project identity and file modification times so unchanged reviewed
output does not become spuriously stale. Older archives without modification
times require a fresh review. Use the original project identifier in the destination.
Test restoration into an isolated projects root before relying on a backup.
Do not launch the project until the restore command has returned successfully.

Restoring elsewhere is useful for **inspection**, not transparent paid-job
migration. Existing artifact paths and approval/provider journals can bind the
original canonical directory. Resume at the original absolute project path
after safely moving aside the old copy. A different path requires an explicit
reviewed migration/reconciliation; this tool does not rewrite approval identities
or silently authorize spending from a copied ledger.

The default size limit is 20 GiB; use `--max-bytes` explicitly for larger
trusted projects. Store backups on access-controlled storage and apply an
appropriate retention policy. The tool does not upload anything, change
storage permissions, or retrieve encryption keys.

## Release acceptance

Before unattended work, close every applicable blocker in the
[dated audit](audits/2026-09-15-production-readiness.md), record resolved
versions, and exercise a real approved workflow on the intended account and
hardware. Validate spending limits, recovery of an ambiguous remote task,
project restore, measured output duration, full decode, audio/captions,
human creative review, rights/provenance, and a final approved export.

Keep publication explicit and separate. No scheduler integration or public
deployment is automatically authorized by a passing local release gate.
