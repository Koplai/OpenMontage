"""Production reliability regressions through the actual ASGI application."""

import asyncio
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from backlot import __main__ as cli
from backlot import server as server_mod
from backlot import state as state_mod
from tests.backlot.test_server import client, projects_root, _make_project, _write_json  # noqa: F401


@pytest.mark.parametrize(("filename", "payload", "scope"), [
    ("checkpoint_script.json", {"metadata": ["bad"], "status": "in_progress"}, ".metadata"),
    ("checkpoint_script.json", {"artifacts": ["bad"]}, ".artifacts"),
    ("checkpoint_script.json", {"review": 4, "cost_snapshot": "bad"}, ".review"),
    ("checkpoint_script.json", {"artifacts": {"script": 9}}, ".artifacts.script"),
    ("project.json", {"pipeline_type": ["bad"]}, ".pipeline_type"),
    ("artifacts/scene_plan.json", {"scenes": [
        {"id": "bad", "start_seconds": "zero", "end_seconds": 3},
        {"id": "good", "start_seconds": 3, "end_seconds": 6},
    ]}, ".scenes[0].start_seconds"),
    ("artifacts/scene_plan.json", {"scenes": [{"id": 0}], "metadata": ["bad"]}, ".metadata"),
    ("artifacts/scene_plan.json", {"scenes": [{"start_seconds": 5, "end_seconds": 2}]},
     ".scenes[0].end_seconds"),
    ("artifacts/script.json", {"sections": [None, {"text": "readable"}]}, ".sections[0]"),
    ("artifacts/script.json", {"sections": "bad"}, ".sections"),
    ("artifacts/asset_manifest.json", {"assets": [{"path": 42}]}, ".assets[0].path"),
    ("artifacts/decision_log.json", {"decisions": [{"options_considered": "bad"}]},
     ".decisions[0].options_considered"),
    ("artifacts/asset_manifest.json", {"total_cost_usd": float("nan")}, ".total_cost_usd"),
])
def test_nested_damage_is_scoped_not_500(client, projects_root, filename, payload, scope):
    project = _make_project(projects_root)
    _write_json(project / filename, payload)
    _write_json(project / "artifacts" / "brief.json", {"hook": "Readable sibling"})
    (project / "renders" / "final.mp4").write_bytes(b"0123456789")
    response = client.get("/api/project/film/state")
    assert response.status_code == 200
    state = response.json()
    assert state["artifacts"]["brief"]["hook"] == "Readable sibling"
    assert any(d["scope"] == filename + scope for d in state["diagnostics"]), state["diagnostics"]
    assert client.get("/api/projects").json()[0]["diagnostics"]
    assert client.get("/media/film/renders/final.mp4", headers={"Range": "bytes=2-5"}).content == b"2345"


def test_bad_json_and_events_keep_readable_state(client, projects_root):
    project = _make_project(projects_root)
    (project / "checkpoint_assets.json").write_text("{truncated")
    (project / "events.jsonl").write_text('[]\nnull\n{"event":"finish","tool":"synthetic"}\n')
    state = client.get("/api/project/film/state").json()
    assert state["stages"]
    assert state["events"] == [{"event": "finish", "tool": "synthetic"}]
    assert {d["scope"] for d in state["diagnostics"]} >= {
        "checkpoint_assets.json", "events.jsonl[0]", "events.jsonl[1]",
    }


def test_canonical_artifact_does_not_hide_damaged_checkpoint_copy(client, projects_root):
    project = _make_project(projects_root)
    _write_json(project / "artifacts" / "script.json", {"sections": [{"text": "Readable canonical"}]})
    _write_json(project / "checkpoint_script.json", {"artifacts": {"script": {"sections": "bad"}}})
    state = client.get("/api/project/film/state").json()
    assert state["artifacts"]["script"]["sections"][0]["text"] == "Readable canonical"
    assert state["diagnostics"][0]["scope"] == "checkpoint_script.json.artifacts.script.sections"


def test_symlink_policy_for_projects_json_events_and_media(client, projects_root, tmp_path):
    project = _make_project(projects_root)
    outside = tmp_path / "outside"
    outside.mkdir()
    _write_json(outside / "script.json", {"title": "OUTSIDE SYNTHETIC"})
    (outside / "final.mp4").write_bytes(b"outside-synthetic")
    (outside / "events.jsonl").write_text('{"tool":"outside"}\n')
    (projects_root / "linked").symlink_to(outside, target_is_directory=True)
    for url in ("/api/project/linked/state", "/api/project/linked/events", "/media/linked/final.mp4"):
        assert client.get(url).status_code == 403
    assert [p["project_id"] for p in client.get("/api/projects").json()] == ["film"]
    assert [p["project_id"] for p in state_mod.list_projects(projects_root)] == ["film"]

    (project / "artifacts" / "script.json").symlink_to(outside / "script.json")
    (project / "renders" / "escape.mp4").symlink_to(outside / "final.mp4")
    (project / "events.jsonl").symlink_to(outside / "events.jsonl")
    response = client.get("/api/project/film/state")
    assert "OUTSIDE SYNTHETIC" not in response.text
    assert "script" not in response.json()["artifacts"]
    assert response.json()["media"]["renders"] == []
    assert response.json()["events"] == []
    assert client.get("/media/film/renders/escape.mp4").status_code == 403
    assert client.get("/thumb/film/renders/escape.mp4").status_code == 403
    assert len(response.json()["diagnostics"]) >= 2

    # In-project canonical/media links and in-workspace project aliases work.
    _write_json(project / "artifacts" / "source.json", {"title": "Local script", "sections": []})
    (project / "artifacts" / "script.json").unlink()
    (project / "artifacts" / "script.json").symlink_to(project / "artifacts" / "source.json")
    (project / "renders" / "final.mp4").write_bytes(b"0123456789")
    (project / "renders" / "alias.mp4").symlink_to(project / "renders" / "final.mp4")
    (projects_root / "alias").symlink_to(project, target_is_directory=True)
    assert client.get("/api/project/alias/state").json()["artifacts"]["script"]["title"] == "Local script"
    response = client.get("/media/alias/renders/alias.mp4", headers={"Range": "bytes=-3"})
    assert response.status_code == 206 and response.content == b"789"


def test_looping_symlinks_are_diagnostics_or_forbidden(client, projects_root):
    project = _make_project(projects_root)
    (project / "artifacts" / "script.json").symlink_to("script.json")
    response = client.get("/api/project/film/state")
    assert response.status_code == 200 and response.json()["diagnostics"]
    assert client.get("/media/film/artifacts/script.json").status_code == 403


def test_cache_age_size_removal_and_elapsed_status(client, projects_root, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(server_mod, "monotonic", lambda: clock[0])
    monkeypatch.setattr(server_mod, "SUMMARY_CACHE_MAX", 2)
    for i in range(3):
        _make_project(projects_root, f"film{i}")
    assert len(client.get("/api/projects").json()) == 3
    assert len(server_mod._summary_cache) == 2
    monkeypatch.setattr(server_mod, "SUMMARY_CACHE_MAX", 128)
    client.get("/api/projects")
    project = projects_root / "film2"
    _write_json(project / "project.json", {"title": "Changed without watcher"})
    assert not any(p["title"] == "Changed without watcher" for p in client.get("/api/projects").json())
    clock[0] += server_mod.SUMMARY_TTL_SECONDS + 1
    assert any(p["title"] == "Changed without watcher" for p in client.get("/api/projects").json())
    # Expire wall-clock state without touching files.
    future = time.time() + state_mod.STALL_WINDOW_SECONDS + 1
    monkeypatch.setattr(server_mod.time, "time", lambda: future)
    clock[0] += server_mod.SUMMARY_TTL_SECONDS + 1
    assert not any(p["live"] for p in client.get("/api/projects").json())
    import shutil
    shutil.rmtree(projects_root)
    assert client.get("/api/projects").json() == []
    assert server_mod._summary_cache == {}


def test_live_and_stalled_recomputed_on_state_requests(client, projects_root, monkeypatch):
    project = _make_project(projects_root)
    _write_json(project / "checkpoint_script.json", {"status": "in_progress"})
    now = time.time()
    for path in [project / "checkpoint_script.json"]:
        os.utime(path, (now, now))
    state = client.get("/api/project/film/state").json()
    assert state["live"]
    monkeypatch.setattr(server_mod.time, "time", lambda: now + state_mod.STALL_WINDOW_SECONDS + 1)
    state = client.get("/api/project/film/state").json()
    assert not state["live"]
    assert next(s for s in state["stages"] if s["name"] == "script")["stalled"]


def test_watcher_recovers_initially_absent_root(projects_root, monkeypatch):
    projects_root.rmdir()
    monkeypatch.setattr(server_mod, "WATCH_RETRY_SECONDS", 0.02)

    async def exercise():
        q = server_mod.hub.subscribe("film")
        task = asyncio.create_task(server_mod._watch_projects())
        try:
            await asyncio.sleep(0.05)
            assert not task.done()
            project = _make_project(projects_root)
            for i in range(40):
                _write_json(project / "checkpoint_script.json", {"status": "in_progress", "tick": i})
                try:
                    assert await asyncio.wait_for(q.get(), timeout=0.15) == "film"
                    break
                except asyncio.TimeoutError:
                    continue
            else:
                pytest.fail("watcher did not observe writes after root creation")
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            server_mod.hub.unsubscribe(q)

    asyncio.run(exercise())
    assert server_mod._project_of_change(str(projects_root) + "-other/film/a.json") is None


@pytest.mark.parametrize("path", ["/api/library/events", "/api/project/film/events"])
def test_actual_asgi_sse_hello_change_heartbeat_and_cleanup(projects_root, monkeypatch, path):
    _make_project(projects_root)
    monkeypatch.setattr(server_mod, "SSE_HEARTBEAT_SECONDS", 0.01)

    async def exercise():
        messages = []
        incoming = asyncio.Queue()
        await incoming.put({"type": "http.request", "body": b"", "more_body": False})

        async def send(message):
            if message["type"] != "http.response.body" or not message.get("body"):
                return
            for chunk in message["body"].decode().split("\n\n"):
                if not chunk:
                    continue
                data = json.loads(chunk.removeprefix("data: "))
                messages.append(data["type"])
                if data["type"] == "hello":
                    server_mod.hub.publish("film")
                if data["type"] == "heartbeat":
                    await incoming.put({"type": "http.disconnect"})

        scope = {"type": "http", "asgi": {"version": "3.0"}, "method": "GET", "scheme": "http",
                 "path": path, "raw_path": path.encode(), "query_string": b"", "headers": [],
                 "server": ("127.0.0.1", 80), "client": ("127.0.0.1", 1234), "http_version": "1.1"}
        await asyncio.wait_for(server_mod.create_app()(scope, incoming.get, send), 3)
        assert messages[:3] == ["hello", "change", "heartbeat"]
        assert not server_mod.hub._subscribers

    asyncio.run(exercise())


def test_authored_content_has_opaque_sandbox_even_on_thumb_alias(client, projects_root):
    project = _make_project(projects_root)
    (project / "preview.html").write_text("<script>document.title='local composition'</script>")
    for route in ("media", "thumb"):
        response = client.get(f"/{route}/film/preview.html")
        assert response.status_code == 200
        policy = response.headers["content-security-policy"]
        assert "sandbox allow-scripts;" in policy
        assert "allow-same-origin" not in policy
        assert "connect-src 'none'" in policy
        assert response.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" not in client.get("/p/film").headers.get("content-security-policy", "")


def test_health_probe_rejects_other_app_workspace_and_non_json(projects_root, monkeypatch):
    import lib.paths
    monkeypatch.setattr(lib.paths, "PROJECTS_DIR", projects_root)
    payload = [b"not JSON"]

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(payload[0])

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        port = server.server_address[1]
        assert not cli._server_alive(port)
        for app, root, expected in [
            ("other-app", projects_root, False),
            ("backlot", projects_root.parent, False),
            ("backlot", projects_root, True),
        ]:
            payload[0] = json.dumps({"ok": True, "app": app, "api_version": 1,
                                     "workspace_id": server_mod.workspace_id(root)}).encode()
            assert cli._server_alive(port) is expected
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_cli_does_not_accept_unsafe_bind_options():
    with pytest.raises(SystemExit) as exc:
        cli.main(["serve", "--host", "0.0.0.0"])
    assert exc.value.code == 2


def test_thumbnail_cache_bounded_and_failed_temp_cleaned(client, projects_root, monkeypatch):
    from tests.backlot.test_server import _write_png
    monkeypatch.setattr(server_mod, "THUMB_CACHE_MAX_FILES", 2)
    project = _make_project(projects_root)
    for i in range(4):
        _write_png(project / f"{i}.png")
        assert client.get(f"/thumb/film/{i}.png").status_code == 200
    assert len(list(server_mod.THUMB_CACHE_DIR.glob("*.jpg"))) == 2
    assert not list(server_mod.THUMB_CACHE_DIR.glob("*.tmp.jpg"))
    (project / "renders" / "bad.mp4").write_bytes(b"not a video")
    assert client.get("/thumb/film/renders/bad.mp4").status_code == 404
    assert not list(server_mod.THUMB_CACHE_DIR.glob("*.tmp.jpg"))
