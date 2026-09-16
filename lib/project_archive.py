"""Hash-verified, non-overwriting backups for paused local production projects."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
from zipfile import BadZipFile, ZipFile, ZIP_DEFLATED

DEFAULT_MAX_BYTES = 20 * 1024**3
MAX_FILES = 100_000


def _safe_relative(name: str) -> Path:
    path = PurePosixPath(name)
    if (
        not name or "\\" in name or ":" in name or path.is_absolute()
        or any(part in {"", ".", ".."} for part in name.split("/"))
    ):
        raise ValueError(f"Unsafe archive path: {name!r}")
    return Path(*path.parts)


def _is_secret_file(path: Path) -> bool:
    return (
        any(part.startswith(".env") for part in path.parts)
        or path.suffix.lower() in {".pem", ".key", ".p12"}
        or path.name in {"credentials", "credentials.json", ".youtube-token.json"}
        or "service-account" in path.name
        or "service_account" in path.name
    )


def _copy_hash(source, destination, limit: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while chunk := source.read(1024 * 1024):
        size += len(chunk)
        if size > limit:
            raise ValueError("Archive exceeds the configured byte limit")
        destination.write(chunk)
        digest.update(chunk)
    return digest.hexdigest(), size


def backup_project(project: Path, destination: Path, *, max_bytes: int = DEFAULT_MAX_BYTES) -> Path:
    from lib.checkpoint import project_snapshot

    if Path(project).is_symlink():
        raise ValueError("Backup refuses a symlink project root")
    with project_snapshot(project):
        return _backup_project(project, destination, max_bytes=max_bytes)


def _backup_project(project: Path, destination: Path, *, max_bytes: int) -> Path:
    project, destination = Path(project).resolve(), Path(destination).absolute()
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    if not (project / "project.json").is_file():
        raise ValueError("Backup requires an initialized project.json")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    if destination.resolve().is_relative_to(project):
        raise ValueError("Backup destination must be outside the project")
    for checkpoint in project.glob("checkpoint_*.json"):
        if checkpoint.is_symlink():
            raise ValueError("Symlink checkpoints cannot be backed up")
        if json.loads(checkpoint.read_text(encoding="utf-8")).get("status") == "in_progress":
            raise ValueError("Pause/checkpoint the production before backing it up")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".openmontage-backup-", dir=destination.parent) as temporary:
        archive = Path(temporary) / "project.zip"
        manifest = {"version": 1, "files": {}}
        total = 0
        with ZipFile(archive, "x", compression=ZIP_DEFLATED) as output:
            for path in sorted(project.rglob("*")):
                relative = path.relative_to(project)
                if path.is_symlink():
                    raise ValueError(f"Backup refuses symlink: {relative}")
                if path.is_dir():
                    continue
                if not path.is_file() or _is_secret_file(relative):
                    raise ValueError(f"Backup refuses secret or special file: {relative}")
                _safe_relative(relative.as_posix())
                if len(manifest["files"]) >= MAX_FILES:
                    raise ValueError("Too many files in backup")
                with path.open("rb") as source, output.open(f"files/{relative.as_posix()}", "w") as target:
                    digest, size = _copy_hash(source, target, max_bytes - total)
                total += size
                manifest["files"][relative.as_posix()] = {
                    "sha256": digest, "size": size, "mode": stat.S_IMODE(path.stat().st_mode) & 0o777,
                }
            output.writestr("manifest.json", json.dumps(manifest, sort_keys=True))
        # A hard link is an atomic no-clobber publication, unlike replace().
        os.link(archive, destination)
    return destination


def restore_project(archive: Path, destination: Path, *, max_bytes: int = DEFAULT_MAX_BYTES) -> Path:
    destination = Path(destination).absolute()
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(archive) as source:
        infos = source.infolist()
        names = [entry.filename for entry in infos]
        if len(names) != len(set(names)) or len(names) > MAX_FILES + 1:
            raise ValueError("Duplicate entries or too many files in backup")
        if source.getinfo("manifest.json").file_size > 8 * 1024**2:
            raise ValueError("Backup manifest is too large")
        if sum(entry.file_size for entry in infos) > max_bytes + 8 * 1024**2:
            raise ValueError("Archive exceeds the configured byte limit")
        manifest = json.loads(source.read("manifest.json"))
        if not isinstance(manifest, dict):
            raise ValueError("Invalid project backup manifest")
        files = manifest.get("files")
        if manifest.get("version") != 1 or not isinstance(files, dict) or "project.json" not in files:
            raise ValueError("Invalid project backup manifest")
        if set(names) != {"manifest.json"} | {f"files/{name}" for name in files}:
            raise ValueError("Backup entries do not match the manifest")
        with tempfile.TemporaryDirectory(prefix=".openmontage-restore-", dir=destination.parent) as temporary:
            staged = Path(temporary) / "project"
            staged.mkdir()
            total = 0
            for name, expected in files.items():
                relative = _safe_relative(name)
                if _is_secret_file(relative):
                    raise ValueError(f"Restore refuses secret file: {relative}")
                info = source.getinfo(f"files/{name}")
                if stat.S_ISLNK(info.external_attr >> 16):
                    raise ValueError("Symlinks cannot be restored")
                if not isinstance(expected, dict) or type(expected.get("size")) is not int:
                    raise ValueError(f"Invalid metadata for {name}")
                mode = expected.get("mode", 0o600)
                if type(mode) is not int or not 0 <= mode <= 0o777:
                    raise ValueError(f"Invalid permissions for {name}")
                target = staged / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(info) as incoming, target.open("xb") as outgoing:
                    digest, size = _copy_hash(incoming, outgoing, max_bytes - total)
                total += size
                if digest != expected.get("sha256") or size != expected["size"]:
                    raise ValueError(f"Backup integrity check failed: {name}")
                target.chmod(mode)
            marker = json.loads((staged / "project.json").read_text(encoding="utf-8"))
            if not isinstance(marker, dict):
                raise ValueError("Restored project marker must be an object")
            # Reserve the name exclusively; the marker only appears at publication.
            destination.mkdir()
            try:
                os.replace(staged, destination)
            except OSError as exc:
                try:
                    destination.rmdir()
                except OSError as cleanup_error:
                    exc.add_note(f"Could not remove the reserved restore directory: {cleanup_error}")
                raise
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("backup", "restore"))
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    args = parser.parse_args()
    operation = backup_project if args.operation == "backup" else restore_project
    try:
        result = operation(args.source, args.destination, max_bytes=args.max_bytes)
    except (OSError, ValueError, KeyError, BadZipFile) as exc:
        parser.exit(1, f"{args.operation} failed: {exc}\n")
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
