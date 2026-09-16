"""Audited render-contract regressions. All media is synthetic; no browser/network."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.base_tool import ToolResult
from tools.video.hyperframes_compose import HyperFramesCompose
from tools.video.video_compose import VideoCompose


def cut(source: Path | str, start=0, end=3, **kwargs):
    return {"id": "cut", "source": str(source), "in_seconds": start,
            "out_seconds": end, **kwargs}


def edit(cuts, runtime="ffmpeg", **kwargs):
    return {"version": "1.0", "render_runtime": runtime, "cuts": cuts,
            "renderer_family": "explainer-data",
            "metadata": {"compose_target": {"width": 320, "height": 240}}, **kwargs}


def probe(path):
    return json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_format", "-show_streams",
        "-of", "json", str(path),
    ]))


@pytest.fixture
def media(tmp_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("requires local FFmpeg")
    video = tmp_path / "source.mp4"
    audio = tmp_path / "short.wav"
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-f", "lavfi",
        "-i", "testsrc2=size=320x240:rate=30:duration=6",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", str(video),
    ], check=True, capture_output=True)
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-f", "lavfi",
        "-i", "sine=frequency=220:duration=1.5", str(audio),
    ], check=True, capture_output=True)
    return video, audio


def test_locked_remotion_never_calls_ffmpeg(monkeypatch, tmp_path):
    tool = VideoCompose()
    monkeypatch.setattr(tool, "_remotion_available", lambda: False)
    monkeypatch.setattr(tool, "_compose", lambda _: pytest.fail("silent runtime swap"))
    result = tool.execute({
        "operation": "render", "edit_decisions": edit([cut("clip.mp4")], "remotion"),
        "asset_manifest": {"assets": []}, "output_path": str(tmp_path / "out.mp4"),
    })
    assert not result.success
    assert "remotion" in result.error.lower() and "unavailable" in result.error.lower()


def test_timeline_separates_source_trim_speed_and_position():
    from lib.render_timeline import normalize_cuts

    cuts = normalize_cuts([cut("a.mp4", 2, 6, speed=2), cut("b.mp4", 0, 3)])
    assert [(c["timeline_start_seconds"], c["timeline_duration_seconds"]) for c in cuts] == [
        (0, 2), (2, 3),
    ]
    assert (cuts[0]["in_seconds"], cuts[0]["out_seconds"], cuts[0]["speed"]) == (2, 6, 2)
    assert HyperFramesCompose._compute_total_duration(cuts) == 5
    assert [s["startSeconds"] for s in VideoCompose._cuts_to_cinematic_scenes(cuts)] == [0, 2]


@pytest.mark.parametrize("overrides", [
    {"speed": 0}, {"speed": float("nan")}, {"out_seconds": 0},
    {"in_seconds": -1}, {"timeline_duration_seconds": 9},
])
def test_invalid_timeline_is_not_silently_shortened(overrides):
    from lib.render_timeline import normalize_cuts

    with pytest.raises(ValueError):
        normalize_cuts([{**cut("a.mp4"), **overrides}])


@pytest.mark.parametrize("field", ["audio_path", "subtitle_path"])
def test_missing_explicit_inputs_fail_before_execute(monkeypatch, tmp_path, field):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    tool = VideoCompose()
    monkeypatch.setattr(tool, "run_command", lambda *a, **k: pytest.fail("executed with missing input"))
    result = tool.execute({
        "operation": "compose", "edit_decisions": edit([cut(source)]),
        "output_path": str(tmp_path / "out.mp4"), field: str(tmp_path / "missing"),
    })
    assert not result.success
    assert "not found" in result.error.lower()


def test_string_subtitle_style_retains_canonical_typography():
    style = VideoCompose._resolve_subtitle_style(
        None, {"subtitles": {"style": "word-by-word", "font": "Test Font", "font_size": 41}}, None,
    )
    assert style["font"] == "Test Font" and style["font_size"] == 41


def test_short_music_preserves_visual_duration_and_real_audio(media, tmp_path):
    source, audio = media
    output = tmp_path / "out.mp4"
    result = VideoCompose().execute({
        "operation": "compose", "edit_decisions": edit([cut(source, 0, 4)]),
        "audio_path": str(audio), "output_path": str(output), "preset": "ultrafast",
    })
    assert result.success, result.error
    info = probe(output)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    assert float(video["duration"]) == pytest.approx(4, abs=0.06)
    assert any(s["codec_type"] == "audio" for s in info["streams"])
    assert result.data["has_mixed_audio"]
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(output), "-f", "null", "-"],
                   check=True, capture_output=True)


@pytest.mark.parametrize("speed", [0.5, 2])
def test_ffmpeg_source_trim_and_speed_preserve_exact_visual_length(media, tmp_path, speed):
    source, _ = media
    output = tmp_path / f"speed-{speed}.mp4"
    result = VideoCompose().execute({
        "operation": "compose", "edit_decisions": edit([cut(source, 2, 4, speed=speed)]),
        "output_path": str(output), "preset": "ultrafast",
    })
    assert result.success, result.error
    stream = next(s for s in probe(output)["streams"] if s["codec_type"] == "video")
    assert float(stream["duration"]) == pytest.approx(2 / speed, abs=0.06)


def test_ffconcat_directory_apostrophe(media, tmp_path):
    source, _ = media
    output = tmp_path / "quote's-dir" / "out.mp4"
    result = VideoCompose().execute({
        "operation": "compose", "edit_decisions": edit([cut(source, 1, 3)]),
        "output_path": str(output), "preset": "ultrafast",
    })
    assert result.success, result.error
    assert float(probe(output)["format"]["duration"]) == pytest.approx(2, abs=0.1)


def test_half_second_render_is_not_an_accepted_deliverable(media, tmp_path):
    source, _ = media
    result = VideoCompose().execute({
        "operation": "render", "edit_decisions": edit([cut(source, 0, 0.5)]),
        "asset_manifest": {"assets": []}, "output_path": str(tmp_path / "draft.mp4"),
        "preset": "ultrafast",
    })
    assert not result.success
    assert result.data["final_review"]["status"] in {"revise", "fail"}
    assert result.data["deliverable_accepted"] is False


def test_review_binds_exact_bytes_and_does_not_infer_burn_from_source(media, tmp_path):
    source, _ = media
    subtitle = tmp_path / "captions.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nNot actually burned\n")
    review = VideoCompose()._run_final_review(
        source, edit([cut(source)], subtitles={"enabled": True, "source": str(subtitle)}),
    )
    assert review["output_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert review["output_size_bytes"] == source.stat().st_size
    assert review["checks"]["subtitle_check"]["subtitles_present"] is False
    assert review["status"] != "pass"


def test_hyperframes_same_size_basename_collisions(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / "assets").mkdir(parents=True)
    sources = []
    for directory, contents in [("one", b"aaaa"), ("two", b"bbbb")]:
        source = tmp_path / directory / "clip.mp4"
        source.parent.mkdir()
        source.write_bytes(contents)
        sources.append(source)
    resolved, _ = HyperFramesCompose()._resolve_and_stage_assets(
        [cut(s) for s in sources], [], workspace,
    )
    assert resolved[0]["source"] != resolved[1]["source"]
    assert [Path(c["source"]).read_bytes() for c in resolved] == [b"aaaa", b"bbbb"]


def test_hyperframes_missing_reference_requires_explicit_draft(tmp_path):
    inputs = {"operation": "scaffold_workspace", "workspace_path": str(tmp_path / "hf"),
              "edit_decisions": edit([cut("missing-asset-id")], "hyperframes")}
    tool = HyperFramesCompose()
    result = tool.execute(inputs)
    assert not result.success and "missing-asset-id" in result.error
    draft = tool.execute({**inputs, "draft": True})
    assert draft.success, draft.error
    assert draft.data["deliverable_accepted"] is False
    assert draft.data["missing_references"] == ["missing-asset-id"]


def test_hyperframes_missing_narration_blocks(tmp_path):
    with pytest.raises(ValueError, match="missing-voice"):
        HyperFramesCompose()._resolve_audio_refs(
            {"narration": {"segments": [{"asset_id": "missing-voice"}]}}, [], tmp_path,
        )


def test_hyperframes_explicit_music_mute(tmp_path):
    source = tmp_path / "music.wav"
    source.write_bytes(b"audio")
    refs = HyperFramesCompose()._resolve_audio_refs(
        {"music": {"asset_id": "m", "volume": 0}},
        [{"id": "m", "path": str(source)}], tmp_path,
    )
    assert refs["music"]["volume"] == 0


def test_hyperframes_html_source_offset_is_not_timeline_position():
    tool = HyperFramesCompose()
    html, _ = tool._cut_to_html(0, {
        **cut("clip.mp4", 2, 5), "timeline_start_seconds": 7,
        "timeline_duration_seconds": 3,
    }, 320, 240)
    assert 'data-start="7"' in html
    assert 'data-media-start="2"' in html
    assert 'data-duration="3"' in html


def test_hyperframes_status_never_executes_package_manager_or_doctor(monkeypatch):
    calls = []

    def passive_only(args, **kwargs):
        calls.append(args)
        assert Path(args[0]).name in {"node", "node.exe"}
        assert args[1:] == ["--version"]
        return subprocess.CompletedProcess(args, 0, "v22.19.0\n", "")

    monkeypatch.setattr(subprocess, "run", passive_only)
    HyperFramesCompose().get_info()
    assert all("doctor" not in c for c in calls)


def test_remotion_zero_exit_does_not_accept_stale_or_invalid_output(monkeypatch, tmp_path):
    output = tmp_path / "out.mp4"
    output.write_bytes(b"old invalid output")
    monkeypatch.setattr(VideoCompose, "run_command", lambda *a, **k: None)
    result = VideoCompose()._remotion_render({
        "composition_data": {"cuts": [cut("", 0, 2, type="text_card", text="Synthetic")]},
        "output_path": str(output),
    })
    assert not result.success
    assert output.read_bytes() == b"old invalid output"


def test_high_level_forwards_approved_inputs_to_hyperframes(monkeypatch, tmp_path):
    source = tmp_path / "clip.mp4"
    source.write_bytes(b"source")
    audio = tmp_path / "mix.wav"
    audio.write_bytes(b"audio")
    subtitles = tmp_path / "captions.srt"
    subtitles.write_text("1\n00:00:00,000 --> 00:00:02,000\nSynthetic\n")
    seen = {}
    monkeypatch.setattr(VideoCompose, "_hyperframes_available", lambda _: True)

    def capture(self, inputs):
        seen.update(inputs)
        return ToolResult(success=False, error="captured without rendering")

    monkeypatch.setattr(HyperFramesCompose, "execute", capture)
    VideoCompose().execute({
        "operation": "render", "edit_decisions": edit([cut(source)], "hyperframes"),
        "asset_manifest": {"assets": []}, "audio_path": str(audio),
        "subtitle_path": str(subtitles), "output_path": str(tmp_path / "out.mp4"),
    })
    assert seen["audio_path"] == str(audio)
    assert seen["subtitle_path"] == str(subtitles)


def test_hyperframes_timeout_preserves_byte_diagnostics(monkeypatch, tmp_path):
    tool = HyperFramesCompose()
    monkeypatch.setattr(tool, "_resolve_npm_package", lambda: {
        "version": "0.8.40", "entry": str(tmp_path / "cli.js"),
    })

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 5, output=b"progress", stderr=b"browser stuck \xff")

    monkeypatch.setattr(subprocess, "run", timeout)
    result = tool._run_hf(["render"], cwd=tmp_path, timeout=5, check=False)
    assert result.returncode == 124
    assert result.stdout == "progress"
    assert "browser stuck" in result.stderr and "timeout after 5s" in result.stderr


def test_hyperframes_executes_only_installed_pinned_entry(monkeypatch, tmp_path):
    from tools.video.hyperframes_compose import HYPERFRAMES_VERSION
    assert HYPERFRAMES_VERSION == "0.8.40"
    entry = tmp_path / "installed-0.8.40" / "cli.js"
    monkeypatch.setattr(HyperFramesCompose, "_resolve_npm_package", classmethod(
        lambda cls: {"version": HYPERFRAMES_VERSION, "entry": str(entry)},
    ))
    calls = []

    def capture(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(subprocess, "run", capture)
    HyperFramesCompose()._run_hf(["doctor"], cwd=None, timeout=5, check=False)
    assert calls[0][1:] == [str(entry), "doctor"]
    assert "npx" not in calls[0] and "npm" not in calls[0]


def test_hyperframes_speed_is_materialized_without_losing_trim(media, tmp_path):
    source, _ = media
    workspace = tmp_path / "hf"
    (workspace / "assets").mkdir(parents=True)
    tool = HyperFramesCompose()
    resolved, _ = tool._resolve_and_stage_assets([cut(source, 2, 6, speed=2)], [], workspace)
    retimed = Path(resolved[0]["source"])
    assert retimed != source
    stream = next(s for s in probe(retimed)["streams"] if s["codec_type"] == "video")
    assert float(stream["duration"]) == pytest.approx(2, abs=0.06)
    html, _ = tool._cut_to_html(0, resolved[0], 320, 240)
    assert 'data-start="0"' in html and 'data-media-start="0"' in html
    assert 'data-duration="2"' in html


def test_presenter_adapter_preserves_trim_speed_and_stages_video(monkeypatch, media, tmp_path):
    source, _ = media
    seen = {}

    def render(self, args, **kwargs):
        props = json.loads(Path(next(a.split("=", 1)[1] for a in args if a.startswith("--props="))).read_text())
        seen.update(props)
        public = Path(next(a.split("=", 1)[1] for a in args if a.startswith("--public-dir=")))
        assert (public / props["videoSrc"]).read_bytes() == source.read_bytes()
        subprocess.run([
            "ffmpeg", "-v", "error", "-y", "-ss", "2", "-t", "4", "-i", str(source),
            "-vf", "setpts=(PTS-STARTPTS)/2,fps=30", "-af", "atempo=2",
            "-t", "2", "-c:v", "libx264", "-preset", "ultrafast",
            args[args.index("render") + 3],
        ], check=True, capture_output=True)

    monkeypatch.setattr(VideoCompose, "run_command", render)
    result = VideoCompose()._remotion_render({
        "edit_decisions": edit([cut(source, 2, 6, speed=2)], "remotion", renderer_family="presenter"),
        "output_path": str(tmp_path / "out.mp4"),
    })
    assert result.success, result.error
    assert "cuts" not in seen
    assert (seen["trimBeforeSeconds"], seen["trimAfterSeconds"], seen["playbackRate"], seen["durationSeconds"]) == (2, 6, 2, 2)


def test_presenter_multiple_cuts_are_explicit_blocker(monkeypatch, media, tmp_path):
    source, _ = media
    monkeypatch.setattr(VideoCompose, "run_command", lambda *a, **k: pytest.fail("unsupported presenter rendered"))
    result = VideoCompose()._remotion_render({
        "edit_decisions": edit([cut(source), cut(source)], "remotion", renderer_family="presenter"),
        "output_path": str(tmp_path / "out.mp4"),
    })
    assert not result.success and "one video cut" in result.error


def test_concurrent_remotion_props_are_isolated(monkeypatch, media, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    source, _ = media
    barrier = Barrier(2)
    seen = []

    def render(self, args, **kwargs):
        props_path = Path(next(a.split("=", 1)[1] for a in args if a.startswith("--props=")))
        props = json.loads(props_path.read_text())
        seen.append(props_path)
        barrier.wait(timeout=10)
        assert json.loads(props_path.read_text()) == props
        subprocess.run([
            "ffmpeg", "-v", "error", "-y", "-i", str(source), "-t", "3",
            "-c:v", "libx264", "-preset", "ultrafast", args[args.index("render") + 3],
        ], check=True, capture_output=True)

    monkeypatch.setattr(VideoCompose, "run_command", render)
    tool = VideoCompose()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda name: tool._remotion_render({
            "edit_decisions": edit([cut(source)], "remotion"),
            "output_path": str(tmp_path / f"{name}.mp4"),
        }), ["a", "b"]))
    assert all(r.success for r in results), [r.error for r in results]
    assert seen[0] != seen[1]
    assert all(not path.exists() for path in seen)
    assert all((tmp_path / f"{name}.mp4").is_file() for name in ["a", "b"])


@pytest.mark.parametrize("operation", ["render", "render_existing"])
def test_hyperframes_zero_exit_rejects_stale_output(monkeypatch, tmp_path, operation):
    workspace = tmp_path / "hf"
    workspace.mkdir()
    (workspace / "index.html").write_text("<html>synthetic</html>")
    output = tmp_path / "out.mp4"
    output.write_bytes(b"previous invalid output")
    tool = HyperFramesCompose()
    monkeypatch.setattr(tool, "_runtime_check", lambda: {"runtime_available": True})
    for method in ("_scaffold", "_lint", "_validate", "_check"):
        monkeypatch.setattr(tool, method, lambda *a: ToolResult(success=True))
    monkeypatch.setattr(tool, "_run_hf", lambda *a, **k: subprocess.CompletedProcess([], 0, "", ""))
    result = tool.execute({"operation": operation, "workspace_path": str(workspace), "output_path": str(output)})
    assert not result.success
    assert output.read_bytes() == b"previous invalid output"


def test_typescript_timeline_matches_canonical_python():
    """Execute the pure TS timeline adapter via the already installed compiler."""
    repo = Path(__file__).resolve().parents[2]
    composer = repo / "remotion-composer"
    if not shutil.which("node") or not (composer / "node_modules/typescript").is_dir():
        pytest.skip("requires installed TypeScript, no installation attempted")
    script = """
const fs = require('fs'), ts = require('typescript');
const code = ts.transpileModule(fs.readFileSync('src/lib/timeline.ts', 'utf8'),
  {compilerOptions: {module: ts.ModuleKind.CommonJS}}).outputText;
const m = {exports: {}};
new Function('exports', 'require', 'module', code)(m.exports, require, m);
const cuts = [{in_seconds: 2, out_seconds: 6, speed: 2},
              {in_seconds: 0, out_seconds: 3}];
const normalized = m.exports.normalizeCuts(cuts);
console.log(JSON.stringify({normalized, frames: m.exports.timelineFrames(cuts, 30)}));
"""
    result = json.loads(subprocess.check_output(["node", "-e", script], cwd=composer))
    assert result["frames"] == 150
    assert [(c["timeline_start_seconds"], c["timeline_duration_seconds"], c["source_in_seconds"])
            for c in result["normalized"]] == [(0, 2, 2), (2, 3, 0)]


def test_ffmpeg_first_frame_uses_source_trim_not_zero(media, tmp_path):
    source, _ = media
    output = tmp_path / "trim.mp4"
    result = VideoCompose().execute({
        "operation": "compose", "edit_decisions": edit([cut(source, 2, 4)]),
        "output_path": str(output), "preset": "ultrafast", "crf": 12,
    })
    assert result.success, result.error

    def pixels(path, seconds):
        return subprocess.check_output([
            "ffmpeg", "-v", "error", "-ss", str(seconds), "-i", str(path),
            "-frames:v", "1", "-vf", "scale=32:24", "-pix_fmt", "rgb24", "-f", "rawvideo", "-",
        ])

    actual, wanted, wrong = pixels(output, 0), pixels(source, 2), pixels(source, 0)
    correct_error = sum(abs(a - b) for a, b in zip(actual, wanted))
    wrong_error = sum(abs(a - b) for a, b in zip(actual, wrong))
    assert correct_error < wrong_error / 4


def test_authored_hyperframes_missing_local_reference_blocks_before_cli(monkeypatch, tmp_path):
    workspace = tmp_path / "hf"
    workspace.mkdir()
    (workspace / "index.html").write_text('<video src="missing.mp4"></video>')
    tool = HyperFramesCompose()
    monkeypatch.setattr(tool, "_runtime_check", lambda: {"runtime_available": True})
    monkeypatch.setattr(tool, "_check", lambda *a: pytest.fail("CLI executed with missing media"))
    result = tool.execute({
        "operation": "render_existing", "workspace_path": str(workspace),
        "output_path": str(tmp_path / "out.mp4"),
    })
    assert not result.success and "missing.mp4" in result.error


def test_short_source_cannot_be_accepted_as_long_timeline(media, tmp_path):
    source, _ = media
    result = VideoCompose().execute({
        "operation": "compose", "edit_decisions": edit([cut(source, 4, 10)]),
        "output_path": str(tmp_path / "out.mp4"), "preset": "ultrafast",
    })
    assert not result.success
    assert not (tmp_path / "out.mp4").exists()


def test_subtitles_are_burned_or_block_before_visual_render(media, tmp_path, monkeypatch):
    source, _ = media
    subtitle = tmp_path / "quote's captions.srt"
    subtitle.write_text("1\n00:00:00,000 --> 00:00:03,000\nSynthetic subtitle\n")
    filters = subprocess.check_output(["ffmpeg", "-hide_banner", "-filters"], text=True)
    tool = VideoCompose()
    if " subtitles " not in filters:
        monkeypatch.setattr(tool, "run_command", lambda *a, **k: pytest.fail("render started without libass"))
    output = tmp_path / "captioned.mp4"
    result = tool.execute({
        "operation": "compose", "edit_decisions": edit([cut(source)]),
        "subtitle_path": str(subtitle), "output_path": str(output),
    })
    if " subtitles " in filters:
        assert result.success, result.error
        assert result.data["has_subtitles"]
        assert output.is_file()
    else:
        assert not result.success and "libass" in result.error
        assert not output.exists()


def test_requested_public_dir_remains_read_only(monkeypatch, media, tmp_path):
    source, _ = media
    public = tmp_path / "public"
    public.mkdir()
    (public / "keep.txt").write_text("authored input")
    seen = {}

    def render(self, args, **kwargs):
        seen["public"] = Path(next(a.split("=", 1)[1] for a in args if a.startswith("--public-dir=")))
        shutil.copy2(source, args[args.index("render") + 3])

    monkeypatch.setattr(VideoCompose, "run_command", render)
    result = VideoCompose()._remotion_render({
        "edit_decisions": edit([cut(source, 0, 6)], "remotion"),
        "public_dir": str(public), "output_path": str(tmp_path / "out.mp4"),
    })
    assert result.success, result.error
    assert seen["public"] != public
    assert [p.name for p in public.iterdir()] == ["keep.txt"]


def test_concurrent_ffmpeg_segments_are_isolated(monkeypatch, media, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    source, _ = media
    barrier = Barrier(2)
    directories = []
    tool = VideoCompose()
    real_run = tool.run_command

    def run(args, **kwargs):
        output = Path(args[-1])
        if output.name == "seg_0000.mp4":
            directories.append(output.parent)
            barrier.wait(timeout=10)
        return real_run(args, **kwargs)

    monkeypatch.setattr(tool, "run_command", run)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda i: tool.execute({
            "operation": "compose", "edit_decisions": edit([cut(source, i, i + 2)]),
            "output_path": str(tmp_path / f"output-{i}.mp4"), "preset": "ultrafast",
        }), [0, 2]))
    assert all(r.success for r in results), [r.error for r in results]
    assert len(set(directories)) == 2
    assert all(not d.exists() for d in directories)


def test_hyperframes_default_output_stays_in_workspace(monkeypatch, media, tmp_path):
    source, _ = media
    workspace = tmp_path / "hf"
    workspace.mkdir()
    (workspace / "index.html").write_text('<main data-composition-id="root"></main>')
    tool = HyperFramesCompose()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(tool, "_runtime_check", lambda: {"runtime_available": True})
    monkeypatch.setattr(tool, "_check", lambda *a: ToolResult(success=True))

    def render(args, **kwargs):
        shutil.copy2(source, args[args.index("--output") + 1])
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(tool, "_run_hf", render)
    result = tool.execute({"operation": "render_existing", "workspace_path": str(workspace)})
    assert result.success, result.error
    assert Path(result.data["output"]) == workspace / "renders" / "final.mp4"
