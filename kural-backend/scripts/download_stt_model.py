#!/usr/bin/env python
"""Download a pinned Whisper (CTranslate2) model into backend/data/models/whisper/<name>.

Run from the repository root:
    .\\.venv\\Scripts\\python.exe scripts\\download_stt_model.py --model small --allow-download

Safety:
- Nothing touches the network unless --allow-download is given (otherwise it only
  prints what it would fetch).
- Only the pinned commit and only the files listed in MODELS are fetched, with no
  Hugging Face token or cached credentials.
- Everything is downloaded into a staging folder and checked first: exact size and
  hash of every file (SHA-256 for the LFS weight file, git blob SHA-1 for the others)
  and no unexpected files. Only a fully verified folder is moved into place.
- The Kural app never downloads anything; it loads this folder with
  local_files_only=True. `--verify-only` re-checks an installed folder offline.

Exit codes: 0 ok, 1 failure, 2 refused (no --allow-download).
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
MODELS_ROOT = ROOT / "backend" / "data" / "models" / "whisper"
SOURCE_FILE = "KURAL_SOURCE.json"  # written after verification; not part of the manifest
SPARE_BYTES = 200 * 1024 * 1024  # free space required beyond the download itself


@dataclass(frozen=True)
class FileSpec:
    size: int
    # Git blob SHA-1 (Hugging Face "blobId") of the file's content. NOT usable for
    # Git LFS files: there the blobId hashes the ~134-byte LFS pointer text, not
    # the content (verified: it caused a false failure on model.bin). Use None.
    blob_sha1: Optional[str] = None
    # LFS object id = SHA-256 of the content. Used for the weights.
    sha256: Optional[str] = None

    def __post_init__(self) -> None:
        if not (self.blob_sha1 or self.sha256):
            raise ValueError("every manifest file needs at least one content hash")


@dataclass(frozen=True)
class ModelSpec:
    repo: str
    revision: str  # full commit SHA; branches and tags are never used
    license: str
    files: dict[str, FileSpec]

    @property
    def total_bytes(self) -> int:
        return sum(f.size for f in self.files.values())


# Values read from the Hugging Face API at the pinned commit (2026-10-27).
MODELS: dict[str, ModelSpec] = {
    "small": ModelSpec(
        repo="Systran/faster-whisper-small",
        revision="536b0662742c02347bc0e980a01041f333bce120",
        license="MIT",
        files={
            "README.md": FileSpec(1998, "16511f6106ead2fbc3a1480957a217c2661a5a98"),
            "config.json": FileSpec(2370, "e5047537059bd8f182d9ca64c470201585015187"),
            # LFS file: the API's blobId (504a7fe0...) is the pointer's hash, so only SHA-256.
            "model.bin": FileSpec(
                483546902,
                sha256="3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671"),
            "tokenizer.json": FileSpec(2203239, "7818adb6de9fa3064d3ff81226fdd675be1f6344"),
            "vocabulary.txt": FileSpec(459861, "c9074644d9d1205686f16d411564729461324b75"),
        },
    ),
}


def git_blob_sha1(path: Path) -> str:
    """SHA-1 exactly as `git hash-object` computes it: sha1(b"blob <size>\\0" + data)."""
    h = hashlib.sha1()
    h.update(f"blob {path.stat().st_size}\0".encode())
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_dir(directory: Path, spec: ModelSpec) -> list[str]:
    """Return a list of problems (empty = the folder is exactly the pinned model)."""
    if not directory.is_dir():
        return [f"{directory} does not exist"]
    problems: list[str] = []
    present = {p.name for p in directory.iterdir()} - {SOURCE_FILE}
    for name in sorted(present - set(spec.files)):
        problems.append(f"unexpected file: {name}")
    for name, want in spec.files.items():
        path = directory / name
        if not path.is_file():
            problems.append(f"missing: {name}")
            continue
        if path.stat().st_size != want.size:
            problems.append(f"size mismatch: {name} is {path.stat().st_size:,}, expected {want.size:,}")
            continue
        if want.blob_sha1 and git_blob_sha1(path) != want.blob_sha1:
            problems.append(f"git blob SHA-1 mismatch: {name}")
        if want.sha256 and sha256_file(path) != want.sha256:
            problems.append(f"SHA-256 mismatch: {name}")
    return problems


def _download(spec: ModelSpec, staging: Path) -> None:
    """The only function that touches the network. Imported lazily so that
    --verify-only and the tests never load the HTTP stack."""
    os.environ.pop("HF_HUB_OFFLINE", None)  # the app sets this; a download must be allowed to connect
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    from huggingface_hub import snapshot_download

    snapshot_download(
        repo_id=spec.repo, revision=spec.revision, local_dir=str(staging),
        allow_patterns=list(spec.files), token=False,  # token=False: send no stored credentials
    )
    shutil.rmtree(staging / ".cache", ignore_errors=True)  # hub bookkeeping, not model files


def _write_source(directory: Path, name: str, spec: ModelSpec) -> None:
    info = {
        "model": name, "repo": spec.repo, "revision": spec.revision, "license": spec.license,
        "retrieved_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "downloaded_by": "scripts/download_stt_model.py",
        "files": {n: {"size": f.size, "git_blob_sha1": f.blob_sha1,
                      "sha256": sha256_file(directory / n)} for n, f in spec.files.items()},
    }
    (directory / SOURCE_FILE).write_text(json.dumps(info, indent=2), encoding="utf-8")


def _print_plan(name: str, spec: ModelSpec, dest: Path) -> None:
    print(f"Model       : {name}")
    print(f"Repository  : https://huggingface.co/{spec.repo}")
    print(f"Commit      : {spec.revision} (pinned)")
    print(f"Licence     : {spec.license}")
    print(f"Destination : {dest}")
    for fname, f in spec.files.items():
        print(f"  {fname:<16} {f.size:>14,} bytes")
    print(f"Total       : {spec.total_bytes:,} bytes ({spec.total_bytes / 1024 ** 3:.2f} GiB)")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Download and verify a pinned Whisper model (local use only).")
    ap.add_argument("--model", required=True, choices=sorted(MODELS))
    ap.add_argument("--allow-download", action="store_true", help="required before any network access")
    ap.add_argument("--verify-only", action="store_true", help="re-check an installed folder; no network")
    ap.add_argument("--force", action="store_true", help="replace an existing folder")
    args = ap.parse_args(argv)

    spec = MODELS[args.model]
    dest = MODELS_ROOT / args.model

    if args.verify_only:
        problems = verify_dir(dest, spec)
        for p in problems:
            print(f"PROBLEM: {p}")
        print("VERIFIED: matches the pinned model exactly." if not problems else "NOT VERIFIED.")
        return 0 if not problems else 1

    _print_plan(args.model, spec, dest)
    if not args.allow_download:
        print("\nNothing was downloaded. Re-run with --allow-download to fetch it.")
        return 2

    if dest.exists():
        problems = verify_dir(dest, spec)
        if not problems:
            print("\nAlready installed and verified; nothing to do.")
            return 0
        if not args.force:
            print(f"\nRefusing: {dest} exists but does not match the pinned model:")
            for p in problems:
                print(f"  - {p}")
            print("Use --force to replace it.")
            return 1

    MODELS_ROOT.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(MODELS_ROOT).free
    if free < spec.total_bytes + SPARE_BYTES:
        print(f"\nRefusing: only {free:,} bytes free, need {spec.total_bytes + SPARE_BYTES:,}.")
        return 1

    staging = MODELS_ROOT / f".staging-{args.model}-{os.getpid()}"
    try:
        print("\nDownloading (pinned commit, no credentials)...")
        _download(spec, staging)
        problems = verify_dir(staging, spec)
        if problems:
            print("\nVERIFICATION FAILED; nothing was installed:")
            for p in problems:
                print(f"  - {p}")
            return 1
        _write_source(staging, args.model, spec)
        old = None
        if dest.exists():  # only reachable with --force
            old = MODELS_ROOT / f".old-{args.model}-{os.getpid()}"
            os.replace(dest, old)
        try:
            os.replace(staging, dest)
        except Exception:
            if old is not None:
                os.replace(old, dest)  # put the previous install back
            raise
        if old is not None:
            shutil.rmtree(old, ignore_errors=True)
    except Exception as exc:  # network, disk, hub errors: report the type only
        print(f"\nFAILED: {type(exc).__name__}: {str(exc)[:200]}")
        return 1
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    print(f"\nInstalled and verified: {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
