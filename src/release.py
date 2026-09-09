"""Validated immutable release directories with an atomic current.json pointer."""
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from src.io_utils import atomic_json, sha256
from src.quality import validate_csv

REQUIRED_SOURCES = ("drivers", "laps", "stints", "weather", "position", "intervals", "pit", "race_control")


def expected_inventory(bronze_dir):
    expected = []
    for season_dir in sorted(Path(bronze_dir).glob("season=*")):
        sessions_path = season_dir / "sessions.json"
        sessions = json.loads(sessions_path.read_text(encoding="utf-8"))
        if not isinstance(sessions, list):
            raise ValueError(f"Invalid sessions catalogue: {sessions_path}")
        season = int(season_dir.name.split("=")[1])
        for session in sessions:
            if session.get("session_name") == "Race" and session.get("is_cancelled") is not True:
                if session.get("year") != season:
                    raise ValueError(f"Catalogue season mismatch: {session}")
                expected.append((season, session["session_key"]))
    if not expected or len(expected) != len(set(expected)):
        raise ValueError("Empty or duplicate race inventory")
    return sorted(expected)


def input_hashes(bronze_dir):
    root = Path(bronze_dir)
    paths = set()
    for season, session in expected_inventory(root):
        folder = root / f"season={season}"
        paths.update((folder / "meetings.json", folder / "sessions.json"))
        paths.update(folder / f"session={session}" / f"{name}.json" for name in REQUIRED_SOURCES)
    return {p.relative_to(root).as_posix(): sha256(p) for p in sorted(paths)}


def code_hashes():
    root = Path(__file__).resolve().parent.parent
    paths = list((root / "src").glob("*.py"))
    paths += [root / "dags/f1_strategy_pipeline.py", root / "requirements.txt"]
    return {p.relative_to(root).as_posix(): sha256(p) for p in sorted(paths)}


def verify_release(path):
    path = Path(path).resolve()
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    for relative, digest in manifest["outputs"].items():
        target = (path / relative).resolve()
        if not target.is_relative_to(path) or sha256(target) != digest:
            raise ValueError(f"Release integrity failure: {relative}")
    if manifest["quality_status"] != "passed":
        raise ValueError("Release quality was not passed")
    return manifest


def current_release(silver_dir):
    root = Path(silver_dir)
    pointer = json.loads((root / "current.json").read_text(encoding="utf-8"))
    release_id = pointer["release_id"]
    if not re.fullmatch(r"[a-f0-9]{24}", release_id):
        raise ValueError("Invalid release identifier")
    path = root / "releases" / release_id
    verify_release(path)
    return path


def publish_release(bronze_dir, silver_dir):
    from src.silver_pipeline import _build_all_sessions

    root, bronze = Path(silver_dir), Path(bronze_dir)
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".publish.lock"
    try:
        lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(f"Publication locked: {lock}. Check for an active publisher before recovering a stale lock.") from exc
    os.close(lock_fd)
    try:
        inputs, code = input_hashes(bronze), code_hashes()
        fingerprint = hashlib.sha256(json.dumps({"inputs": inputs, "code": code}, sort_keys=True).encode()).hexdigest()[:24]
        releases = root / "releases"
        releases.mkdir(exist_ok=True)
        final = releases / fingerprint
        if final.exists():
            verify_release(final)
            result = {"summary": json.loads((final / "global_validation.json").read_text()), "reports": [], "anomalies": json.loads((final / "anomalies.json").read_text())}
        else:
            with tempfile.TemporaryDirectory(prefix=".building-", dir=releases) as temporary:
                stage = Path(temporary)
                result = _build_all_sessions(bronze, stage)
                quality = validate_csv(stage / "f1_silver_dataset.csv")
                atomic_json(stage / "quality.json", quality)
                if input_hashes(bronze) != inputs or code_hashes() != code:
                    raise RuntimeError("Inputs or code changed during the build; release not published")
                outputs = {p.relative_to(stage).as_posix(): sha256(p) for p in sorted(stage.rglob("*")) if p.is_file()}
                atomic_json(stage / "manifest.json", {
                    "release_id": fingerprint, "schema_version": 2,
                    "inputs": inputs, "code": code, "outputs": outputs,
                    "quality_status": quality["status"], "rows": quality["total_rows"],
                    "dataset_sha256": outputs["f1_silver_dataset.csv"],
                })
                stage.rename(final)
        atomic_json(root / "current.json", {"release_id": fingerprint})
        result["release_path"] = str(final)
        result["release_id"] = fingerprint
        return result
    finally:
        lock.unlink(missing_ok=True)
