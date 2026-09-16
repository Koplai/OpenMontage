"""Browser regressions from the Backlot UI bug bash."""

from __future__ import annotations

import os
import json
import socket
import subprocess
import sys
import time
import urllib.request
from urllib.parse import urlsplit

import pytest

from lib.checkpoint import CANONICAL_STAGE_ARTIFACTS, init_project
from lib.pipeline_loader import get_stage_order, load_pipeline
from scripts import backlot_screenshot_stage
from tests.contracts.test_phase0_contracts import sample_artifact


pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402


APPROVAL_CASES = [
    ("gate-research", "framework-smoke", "research", "research_brief", "Test Topic"),
    ("gate-idea", "hybrid", "idea", "brief", "Did you know?"),
    ("gate-proposal", "cinematic", "proposal", "proposal_packet", "The Surprising Truth About X"),
    ("gate-script", "cinematic", "script", "script", "Hello world"),
    ("gate-scene-plan", "cinematic", "scene_plan", "scene_plan", "Host on camera"),
    ("gate-assets", "cinematic", "assets", "asset_manifest", "asset-1"),
    ("gate-edit", "documentary-montage", "edit", "edit_decisions", "cut-1"),
    ("gate-compose", "cinematic", "compose", "render_report", "renders/output.mp4"),
    ("gate-publish", "cinematic", "publish", "publish_log", "youtube"),
]


def _complete_predecessors(root, project_id: str, pipeline_type: str, stage: str) -> None:
    order = get_stage_order(load_pipeline(pipeline_type))
    for predecessor in order[: order.index(stage)]:
        artifact_name = CANONICAL_STAGE_ARTIFACTS.get(predecessor)
        if artifact_name:
            artifact = sample_artifact(artifact_name)
            if artifact_name == "edit_decisions":
                artifact["render_runtime"] = "ffmpeg"
            artifacts = {artifact_name: artifact}
        else:
            artifacts = {}
        backlot_screenshot_stage.write_staged_checkpoint(
            root,
            project_id,
            predecessor,
            "completed",
            artifacts,
            pipeline_type=pipeline_type,
            human_approved=True,
        )


def _build_approval_projects(root) -> None:
    for project_id, pipeline_type, stage, artifact_name, _visible_text in APPROVAL_CASES:
        artifact = sample_artifact(artifact_name)
        if artifact_name == "edit_decisions":
            artifact["render_runtime"] = "ffmpeg"
        review_summary = (
            {
                "critical": 0,
                "suggestions": 1,
                "nitpicks": 0,
                "review_focus_met": "9/9",
                "schema_validation": "proposal_packet PASS",
            }
            if stage == "proposal"
            else "Artifact is ready for human review."
        )
        init_project(
            project_id,
            title=f"Approval fixture: {stage}",
            pipeline_type=pipeline_type,
            pipeline_dir=root,
        )
        _complete_predecessors(root, project_id, pipeline_type, stage)
        backlot_screenshot_stage.write_staged_checkpoint(
            root,
            project_id,
            stage,
            "awaiting_human",
            {artifact_name: artifact},
            pipeline_type=pipeline_type,
            review={
                "round": 1,
                "decision": "pass",
                "critical": 0,
                "suggestions": 1,
                "nitpicks": 0,
                "summary": review_summary,
            },
        )

    # A manifest-declared custom stage/artifact proves the fallback is driven
    # by the stage contract rather than a hardcoded canonical-stage list.
    init_project(
        "gate-character-design",
        title="Approval fixture: character design",
        pipeline_type="character-animation",
        pipeline_dir=root,
    )
    _complete_predecessors(
        root,
        "gate-character-design",
        "character-animation",
        "character_design",
    )
    backlot_screenshot_stage.write_staged_checkpoint(
        root,
        "gate-character-design",
        "character_design",
        "awaiting_human",
        {"character_design": {
            "version": "1.0",
            "characters": [{
                "id": "ada",
                "display_name": "Ada",
                "role": "explorer",
                "body_type": "round",
                "style": "flat graphic",
                "silhouette_notes": "Round explorer with a bright orange field jacket",
                "required_emotions": ["curious"],
                "required_actions": ["wave"],
            }],
        }},
        pipeline_type="character-animation",
    )


@pytest.fixture(scope="module")
def staged_backlot_root(tmp_path_factory):
    root = tmp_path_factory.mktemp("backlot-ui") / "projects"
    backlot_screenshot_stage.build_stage(root)
    _build_approval_projects(root)
    return root


@pytest.fixture(scope="module")
def staged_backlot_server(staged_backlot_root, tmp_path_factory):
    from backlot.server import workspace_id

    if os.name == "nt":
        pytest.skip("This browser fixture reserves a POSIX socket descriptor")
    # Keep the free port reserved until uvicorn takes ownership of the socket.
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    env = dict(os.environ)
    env["OPENMONTAGE_PROJECTS_DIR"] = str(staged_backlot_root)
    cache = tmp_path_factory.mktemp("backlot-thumbs")
    server = subprocess.Popen(
        [sys.executable, "-c",
         "import sys, uvicorn; from pathlib import Path; import backlot.server as s; "
         "import backlot.state as state; "
         "state.LIVE_WINDOW_SECONDS = 2; state.STALL_WINDOW_SECONDS = 4; "
         "s.SSE_HEARTBEAT_SECONDS = 1; s.SUMMARY_TTL_SECONDS = 1; "
         "s.THUMB_CACHE_DIR = Path(sys.argv[2]); "
         "uvicorn.run(s.app, fd=int(sys.argv[1]), log_level='warning')",
         str(listener.fileno()), str(cache)],
        pass_fds=(listener.fileno(),),
        cwd=backlot_screenshot_stage.REPO_ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    listener.close()
    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as response:
                health = json.load(response)
                if health.get("app") == "backlot" and health.get("workspace_id") == workspace_id(staged_backlot_root):
                    break
        except Exception:
            time.sleep(0.2)
    else:
        server.terminate()
        server.wait(timeout=5)
        raise RuntimeError("Backlot server did not become healthy")

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)


def _launch_browser(pw):
    executable = os.environ.get("BACKLOT_TEST_CHROMIUM")
    return pw.chromium.launch(headless=True, **({"executable_path": executable} if executable else {}))


def _local_page(browser, base_url, **kwargs):
    context = browser.new_context(service_workers="block", **kwargs)
    allowed = urlsplit(base_url).netloc
    context.route("**/*", lambda route: route.continue_()
                  if urlsplit(route.request.url).scheme == "http"
                  and urlsplit(route.request.url).netloc == allowed else route.abort())
    context.route_web_socket("**/*", lambda ws: ws.close())
    return context.new_page()


def test_project_pages_fit_mobile_and_tablet_widths(staged_backlot_server):
    project_paths = [
        "/p/signal-in-the-static?static=1",
        "/p/the-slow-orchard?static=1",
        "/p/the-last-lighthouse?static=1",
        "/p/paper-boats?static=1",
        "/p/gate-proposal?static=1",
        "/p/gate-character-design?static=1",
    ]
    viewports = [
        {"width": 390, "height": 844},
        {"width": 768, "height": 1024},
    ]

    with sync_playwright() as pw:
        browser = _launch_browser(pw)
        page = _local_page(browser, staged_backlot_server)
        try:
            for viewport in viewports:
                page.set_viewport_size(viewport)
                for path in project_paths:
                    page.goto(staged_backlot_server + path, wait_until="networkidle")
                    page.wait_for_timeout(300)
                    sizes = page.evaluate(
                        """() => ({
                            scrollWidth: document.documentElement.scrollWidth,
                            clientWidth: document.documentElement.clientWidth
                        })"""
                    )
                    assert sizes["scrollWidth"] <= sizes["clientWidth"], (
                        path,
                        viewport,
                        sizes,
                    )
        finally:
            browser.close()


def test_static_navigation_invalid_route_and_active_takes(staged_backlot_server):
    with sync_playwright() as pw:
        browser = _launch_browser(pw)
        page = _local_page(browser, staged_backlot_server, viewport={"width": 1560, "height": 1000})
        try:
            page.goto(staged_backlot_server + "/?static=1", wait_until="networkidle")
            href = page.locator("a.lib-card").first.get_attribute("href")
            assert href and "static=1" in href

            response = page.goto(
                staged_backlot_server + "/p/..%2FAGENT_GUIDE.md?static=1",
                wait_until="domcontentloaded",
            )
            assert response and response.status == 200
            page.get_by_text("PROJECT NOT FOUND", exact=True).wait_for()

            page.goto(staged_backlot_server + "/p/the-last-lighthouse?static=1", wait_until="networkidle")
            page.wait_for_timeout(300)
            assert page.locator(".takes .tk.active").count() >= 1
        finally:
            browser.close()


@pytest.mark.parametrize(
    ("project_id", "_pipeline_type", "stage", "artifact_name", "visible_text"),
    APPROVAL_CASES,
)
def test_every_canonical_gate_promotes_its_artifact_before_approval(
    staged_backlot_server,
    project_id,
    _pipeline_type,
    stage,
    artifact_name,
    visible_text,
):
    with sync_playwright() as pw:
        browser = _launch_browser(pw)
        page = _local_page(browser, staged_backlot_server, viewport={"width": 1280, "height": 900})
        try:
            page.goto(
                staged_backlot_server + f"/p/{project_id}?static=1",
                wait_until="networkidle",
            )
            review = page.locator(f'.approval-review[data-stage="{stage}"]')
            assert review.is_visible()
            assert review.get_by_text("PENDING APPROVAL", exact=True).is_visible()
            assert "[object Object]" not in review.inner_text()
            artifact = review.locator(f'[data-artifact="{artifact_name}"]')
            assert artifact.is_visible()
            assert visible_text in artifact.inner_text()

            review.get_by_role("button", name="OPEN FULL ARTIFACT").click()
            assert page.locator(".drawer").is_visible()
            assert visible_text in page.locator(".drawer").inner_text()
        finally:
            browser.close()


def test_script_gate_keeps_script_visible_and_marks_pending_approval(staged_backlot_server):
    with sync_playwright() as pw:
        browser = _launch_browser(pw)
        page = _local_page(browser, staged_backlot_server, viewport={"width": 1280, "height": 900})
        try:
            page.goto(staged_backlot_server + "/p/gate-script?static=1", wait_until="networkidle")
            assert page.locator(".script-card").is_visible()
            assert page.locator(".script-pending").inner_text() == "PENDING APPROVAL"
        finally:
            browser.close()


def test_manifest_declared_custom_gate_uses_generic_review_fallback(staged_backlot_server):
    with sync_playwright() as pw:
        browser = _launch_browser(pw)
        page = _local_page(browser, staged_backlot_server, viewport={"width": 1280, "height": 900})
        try:
            page.goto(
                staged_backlot_server + "/p/gate-character-design?static=1",
                wait_until="networkidle",
            )
            review = page.locator('.approval-review[data-stage="character_design"]')
            assert review.is_visible()
            artifact = review.locator('[data-artifact="character_design"]')
            assert artifact.is_visible()
            assert "Ada" in artifact.inner_text()
            assert "Round explorer" in artifact.inner_text()
        finally:
            browser.close()


def test_damaged_nested_state_and_http_failures_have_distinct_messages(
    staged_backlot_server, staged_backlot_root,
):
    project = staged_backlot_root / "damaged"
    project.mkdir()
    (project / "project.json").write_text(json.dumps({"title": "Readable title"}))
    (project / "checkpoint_script.json").write_text(json.dumps({
        "status": "in_progress", "metadata": ["bad"], "artifacts": ["bad"],
    }))
    artifacts = project / "artifacts"
    artifacts.mkdir()
    (artifacts / "scene_plan.json").write_text(json.dumps({"scenes": [
        {"id": "bad", "start_seconds": "zero", "end_seconds": 2},
        {"id": "good", "start_seconds": 2, "end_seconds": 4},
    ]}))
    (artifacts / "script.json").write_text(json.dumps({"sections": [
        None, {"id": 0, "text": "Readable narration", "start_seconds": 2, "end_seconds": 4},
    ]}))
    with sync_playwright() as pw:
        browser = _launch_browser(pw)
        page = _local_page(browser, staged_backlot_server)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            page.goto(staged_backlot_server + "/p/damaged?static=1")
            page.get_by_text("DAMAGED PROJECT STATE", exact=False).wait_for()
            assert "checkpoint_script.json.metadata" in page.locator("body").inner_text()
            assert "Readable narration" in page.locator("body").inner_text()
            assert "PROJECT NOT FOUND" not in page.locator("body").inner_text()
            assert not errors

            page.route("**/api/project/damaged/state", lambda route: route.fulfill(status=503))
            page.reload()
            page.get_by_text("PROJECT STATE UNAVAILABLE", exact=True).wait_for()
            page.goto(staged_backlot_server + "/p/not-present?static=1")
            page.get_by_text("PROJECT NOT FOUND", exact=True).wait_for()
        finally:
            browser.close()


def test_sse_reconnect_reconciles_missed_changes(staged_backlot_server, staged_backlot_root):
    project = staged_backlot_root / "reconnect"
    project.mkdir()
    marker = project / "project.json"
    marker.write_text(json.dumps({"title": "Before reconnect"}))
    with sync_playwright() as pw:
        browser = _launch_browser(pw)
        page = _local_page(browser, staged_backlot_server)
        connections = []
        # A finite SSE response models a dropped connection with no replay log.
        # No change event is delivered; the next hello must trigger a refetch.
        def dropped_connection(route):
            connections.append(route.request.url)
            route.fulfill(status=200, content_type="text/event-stream",
                          body='data: {"type":"hello"}\n\n')
        page.route("**/api/project/reconnect/events", dropped_connection)
        try:
            page.goto(staged_backlot_server + "/p/reconnect")
            page.get_by_role("heading", name="Before reconnect").wait_for()
            page.wait_for_timeout(400)
            marker.write_text(json.dumps({"title": "Recovered missed change"}))
            page.get_by_role("heading", name="Recovered missed change").wait_for(timeout=12000)
            assert len(connections) >= 2
        finally:
            browser.close()


def test_refresh_preserves_paused_and_playing_review(staged_backlot_server, staged_backlot_root):
    project = staged_backlot_root / "the-last-lighthouse"
    with sync_playwright() as pw:
        browser = _launch_browser(pw)
        page = _local_page(browser, staged_backlot_server)
        try:
            page.goto(staged_backlot_server + "/p/the-last-lighthouse")
            page.wait_for_function("document.querySelector('.render-hero video')?.readyState >= 1")
            video = page.locator(".render-hero video")
            video.evaluate("(v) => { v.currentTime = 1.25; v.volume = .4; v.muted = true; v.playbackRate = 1.5; }")
            page.get_by_role("button", name="Switch to light theme").click()
            page.wait_for_function("document.querySelector('.render-hero video')?.currentTime >= 1.2")
            assert video.evaluate("(v) => [v.paused, v.volume, v.muted, v.playbackRate]") == [True, .4, True, 1.5]
            video.evaluate("(v) => v.play()")
            page.get_by_role("button", name="Switch to dark theme").click()
            page.wait_for_function("""() => {
                const v = document.querySelector('.render-hero video');
                return v && !v.paused && v.currentTime >= 1.25;
            }""")
            video.evaluate("(v) => { v.pause(); v.currentTime = 2; }")
            marker = project / "project.json"
            original = marker.read_text()
            try:
                data = json.loads(original)
                data["title"] = "Updated during review"
                marker.write_text(json.dumps(data))
                page.get_by_role("heading", name="Updated during review").wait_for(timeout=10000)
                page.wait_for_function("document.querySelector('.render-hero video')?.currentTime >= 1.9")
                assert video.evaluate("(v) => v.paused")
            finally:
                marker.write_text(original)
        finally:
            browser.close()


def test_authored_html_executes_without_board_origin_access(staged_backlot_server, staged_backlot_root):
    project = staged_backlot_root / "sandbox"
    project.mkdir()
    (project / "preview.html").write_text("""<!doctype html>
        <script>
        window.results = {ran: true};
        try { localStorage.setItem('board-access', 'bad'); results.storage = true; }
        catch { results.storage = false; }
        fetch('/api/projects').then(() => results.api = true).catch(() => results.api = false);
        </script><h1>Synthetic authored preview</h1>""")
    with sync_playwright() as pw:
        browser = _launch_browser(pw)
        page = _local_page(browser, staged_backlot_server)
        try:
            page.goto(staged_backlot_server + "/media/sandbox/preview.html")
            page.wait_for_function("window.results?.api === false")
            assert page.evaluate("window.results") == {"ran": True, "storage": False, "api": False}
        finally:
            browser.close()


def test_elapsed_time_alone_updates_live_idle_and_stalled(staged_backlot_server, staged_backlot_root):
    project = staged_backlot_root / "elapsed"
    project.mkdir()
    checkpoint = project / "checkpoint_script.json"
    with sync_playwright() as pw:
        browser = _launch_browser(pw)
        page = _local_page(browser, staged_backlot_server)
        try:
            # The test server uses shortened thresholds; no writes occur after
            # navigation. Real heartbeat HTTP refetches must age the state.
            checkpoint.write_text(json.dumps({"status": "in_progress"}))
            page.goto(staged_backlot_server + "/p/elapsed")
            page.locator(".slate .live").filter(has_text="LIVE").wait_for()
            page.locator(".slate .live.idle").wait_for(timeout=8000)
            page.locator(".slate .live").filter(has_text="STALLED?").wait_for(timeout=8000)
        finally:
            browser.close()
