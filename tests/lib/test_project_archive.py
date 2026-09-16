import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from lib.project_archive import backup_project, restore_project


@pytest.fixture
def project(tmp_path):
    project = tmp_path / "production"
    (project / "assets").mkdir(parents=True)
    (project / "project.json").write_text('{"project_id":"fixture","pipeline_type":"framework-smoke"}')
    (project / "assets/audio.wav").write_bytes(b"synthetic-not-real-media")
    return project


def test_roundtrip_preserves_project_assets_without_overwriting(project, tmp_path):
    backup = backup_project(project, tmp_path / "backup.zip")
    restored = restore_project(backup, tmp_path / "restored")
    assert (restored / "project.json").read_bytes() == (project / "project.json").read_bytes()
    assert (restored / "assets/audio.wav").read_bytes() == b"synthetic-not-real-media"
    with pytest.raises(FileExistsError):
        restore_project(backup, restored)
    with pytest.raises(FileExistsError):
        backup_project(project, backup)


def test_active_project_is_rejected(project, tmp_path):
    (project / "checkpoint_assets.json").write_text('{"status":"in_progress"}')
    with pytest.raises(ValueError, match="Pause"):
        backup_project(project, tmp_path / "backup.zip")
    assert not (tmp_path / "backup.zip").exists()


def test_pending_checkpoint_transaction_is_not_silently_archived(project, tmp_path):
    (project / ".checkpoint-transaction.json").write_text('{"fixture":"pending"}')
    with pytest.raises(ValueError, match="Recover the pending"):
        backup_project(project, tmp_path / "backup.zip")
    assert not (tmp_path / "backup.zip").exists()


@pytest.mark.parametrize("name", [".env", "credentials", "secret.pem", "cloud-service-account.json"])
def test_secret_files_are_refused(project, tmp_path, name):
    (project / name).write_text("fixture")
    with pytest.raises(ValueError, match="secret"):
        backup_project(project, tmp_path / "backup.zip")
    assert not (tmp_path / "backup.zip").exists()


def test_symlink_and_inside_destination_are_refused(project, tmp_path):
    with pytest.raises(ValueError, match="outside"):
        backup_project(project, project / "backup.zip")
    (project / "link").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="symlink"):
        backup_project(project, tmp_path / "backup.zip")


def test_tampered_data_never_publishes_restored_directory(project, tmp_path):
    good = backup_project(project, tmp_path / "good.zip")
    bad = tmp_path / "bad.zip"
    with ZipFile(good) as source, ZipFile(bad, "w") as target:
        for name in source.namelist():
            target.writestr(name, b"tampered" if name.endswith(".wav") else source.read(name))
    with pytest.raises(ValueError, match="integrity"):
        restore_project(bad, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()


@pytest.mark.parametrize("unsafe", ["../outside", "/absolute", "x\\..\\outside", "C:/outside"])
def test_archive_paths_cannot_escape(tmp_path, unsafe):
    manifest = {"version": 1, "files": {
        "project.json": {"sha256": hashlib.sha256(b"{}").hexdigest(), "size": 2},
        unsafe: {"sha256": hashlib.sha256(b"x").hexdigest(), "size": 1},
    }}
    archive = tmp_path / "crafted.zip"
    with ZipFile(archive, "w") as output:
        output.writestr("manifest.json", json.dumps(manifest))
        output.writestr("files/project.json", b"{}")
        output.writestr(f"files/{unsafe}", b"x")
    with pytest.raises(ValueError, match="Unsafe"):
        restore_project(archive, tmp_path / "restored")
    assert not (tmp_path / "outside").exists()
    assert not (tmp_path / "restored").exists()


def test_limits_are_enforced(project, tmp_path):
    with pytest.raises(ValueError, match="byte limit"):
        backup_project(project, tmp_path / "limited.zip", max_bytes=1)
    backup = backup_project(project, tmp_path / "backup.zip")
    with pytest.raises(ValueError, match="byte limit"):
        restore_project(backup, tmp_path / "restored", max_bytes=1)
    assert not (tmp_path / "restored").exists()


def test_malformed_manifest_shape_fails_before_publication(tmp_path):
    archive = tmp_path / "bad.zip"
    with ZipFile(archive, "w") as target:
        target.writestr("manifest.json", "[]")
    with pytest.raises(ValueError, match="manifest"):
        restore_project(archive, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()


def test_failed_publication_does_not_delete_new_foreign_files(project, tmp_path, monkeypatch):
    backup = backup_project(project, tmp_path / "backup.zip")
    destination = tmp_path / "restored"

    def concurrent_writer(source, target):
        (target / "do-not-delete.txt").write_text("other writer")
        raise OSError("directory became occupied")

    monkeypatch.setattr("lib.project_archive.os.replace", concurrent_writer)
    with pytest.raises(OSError, match="occupied"):
        restore_project(backup, destination)
    assert (destination / "do-not-delete.txt").read_text() == "other writer"
