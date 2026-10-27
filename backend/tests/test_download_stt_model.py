"""Tests for scripts/download_stt_model.py. No real download happens: _download is
replaced by fakes, and the one test that reaches the real one runs under the
network guard."""
import hashlib
import importlib.util
import shutil
from collections import namedtuple
from pathlib import Path

import pytest

from .conftest import NETWORK_ATTEMPTS

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "download_stt_model.py"
spec_ = importlib.util.spec_from_file_location("download_stt_model", SCRIPT)
mod = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(mod)

GOOD = {"config.json": b'{"a": 1}', "model.bin": b"weights" * 100, "tokenizer.json": b"{}"}


def blob(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def fake_spec(files=None) -> "mod.ModelSpec":
    files = files or GOOD
    # Like the real manifest: ordinary files have a git blob SHA-1; the weights (an
    # LFS file) have only a SHA-256.
    return mod.ModelSpec(
        repo="test/repo", revision="a" * 40, license="MIT",
        files={n: (mod.FileSpec(len(d), sha256=hashlib.sha256(d).hexdigest()) if n == "model.bin"
                   else mod.FileSpec(len(d), blob(d)))
               for n, d in files.items()})


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolated models root and a fake spec registered as model 'tiny'."""
    root = tmp_path / "models"
    monkeypatch.setattr(mod, "MODELS_ROOT", root)
    monkeypatch.setattr(mod, "MODELS", {"tiny": fake_spec()})
    return root


def fake_download(content=None, extra=None):
    """Replacement for _download that writes files into the staging folder."""
    def run(spec, staging):
        staging.mkdir(parents=True)
        for n, d in (content or GOOD).items():
            (staging / n).write_bytes(d)
        for n, d in (extra or {}).items():
            (staging / n).write_bytes(d)
        (staging / ".cache").mkdir()
        (staging / ".cache" / "meta").write_text("hub bookkeeping")
        shutil.rmtree(staging / ".cache")  # the real _download removes it too
    return run


def forbid_download(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the network function must not be called")
    monkeypatch.setattr(mod, "_download", boom)


# -- hashing and the shipped manifest ---------------------------------------------
def test_git_blob_sha1_matches_gits_known_values(tmp_path):
    (tmp_path / "hello").write_bytes(b"hello\n")
    (tmp_path / "empty").write_bytes(b"")
    assert mod.git_blob_sha1(tmp_path / "hello") == "ce013625030ba8dba906f756967f9e9ca394464a"
    assert mod.git_blob_sha1(tmp_path / "empty") == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"


def test_shipped_manifest_is_pinned_and_complete():
    small = mod.MODELS["small"]
    assert small.repo == "Systran/faster-whisper-small" and small.license == "MIT"
    assert small.revision == "536b0662742c02347bc0e980a01041f333bce120"
    assert set(small.files) == {"README.md", "config.json", "model.bin", "tokenizer.json", "vocabulary.txt"}
    assert small.files["model.bin"].sha256 == "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671"
    assert small.files["model.bin"].size == 483546902
    assert small.total_bytes == 486214370
    for name, f in small.files.items():
        assert f.size > 0 and (f.blob_sha1 or f.sha256)
        if f.blob_sha1:
            assert len(f.blob_sha1) == 40
    # Regression: for LFS files the API's blobId hashes the pointer file, so the
    # weights must be verified by SHA-256 only.
    assert small.files["model.bin"].blob_sha1 is None


def test_lfs_pointer_hash_is_not_the_content_hash():
    """Documents the bug found on the first real download: the git blob SHA-1 of the
    134-byte LFS pointer equals the API's blobId, so it can never match the weights."""
    oid = "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671"
    pointer = f"version https://git-lfs.github.com/spec/v1\noid sha256:{oid}\nsize 483546902\n".encode()
    assert len(pointer) == 134
    assert blob(pointer) == "504a7fe023f19460564a623887a9f77ea53ac708"


def test_a_manifest_file_without_any_hash_is_refused():
    with pytest.raises(ValueError):
        mod.FileSpec(10)


# -- verification --------------------------------------------------------------------
def make_dir(tmp_path, files=None, name="m"):
    d = tmp_path / name
    d.mkdir()
    for n, data in (files or GOOD).items():
        (d / n).write_bytes(data)
    return d


def test_verify_accepts_exactly_the_pinned_files(tmp_path):
    assert mod.verify_dir(make_dir(tmp_path), fake_spec()) == []


def test_verify_accepts_the_source_record_file(tmp_path):
    d = make_dir(tmp_path)
    (d / mod.SOURCE_FILE).write_text("{}")
    assert mod.verify_dir(d, fake_spec()) == []


@pytest.mark.parametrize("change,fragment", [
    (lambda d: (d / "config.json").unlink(), "missing: config.json"),
    (lambda d: (d / "config.json").write_bytes(b"short"), "size mismatch: config.json"),
    (lambda d: (d / "config.json").write_bytes(b'{"a": 2}'), "git blob SHA-1 mismatch: config.json"),
    (lambda d: (d / "extra.txt").write_bytes(b"x"), "unexpected file: extra.txt"),
])
def test_verify_detects_every_kind_of_problem(tmp_path, change, fragment):
    d = make_dir(tmp_path)
    change(d)
    assert any(fragment in p for p in mod.verify_dir(d, fake_spec()))


def test_verify_checks_sha256_of_the_weights_separately(tmp_path):
    """A file with the right size and the right git blob SHA but a wrong SHA-256
    in the manifest must still fail."""
    s = fake_spec()
    weights = s.files["model.bin"]
    tampered = mod.ModelSpec(s.repo, s.revision, s.license,
                             {**s.files, "model.bin": mod.FileSpec(weights.size, sha256="0" * 64)})
    problems = mod.verify_dir(make_dir(tmp_path), tampered)
    assert problems == ["SHA-256 mismatch: model.bin"]


def test_weights_with_the_right_size_but_different_content_are_rejected(tmp_path):
    d = make_dir(tmp_path, {**GOOD, "model.bin": b"x" * len(GOOD["model.bin"])})
    assert mod.verify_dir(d, fake_spec()) == ["SHA-256 mismatch: model.bin"]


def test_verify_of_a_missing_folder_is_a_problem(tmp_path):
    assert mod.verify_dir(tmp_path / "nope", fake_spec())


# -- refusal and arguments ------------------------------------------------------------
def test_without_allow_download_nothing_happens(env, monkeypatch, capsys):
    forbid_download(monkeypatch)
    assert mod.main(["--model", "tiny"]) == 2
    out = capsys.readouterr().out
    assert "Nothing was downloaded" in out and "test/repo" in out and "a" * 40 in out
    assert not env.exists()  # not even the models folder was created


def test_unknown_model_name_is_rejected(env):
    with pytest.raises(SystemExit) as e:
        mod.main(["--model", "huge", "--allow-download"])
    assert e.value.code == 2


def test_the_real_download_asks_for_the_pinned_commit_and_no_credentials(monkeypatch, tmp_path):
    import huggingface_hub
    seen = {}

    def recorder(**kwargs):
        seen.update(kwargs)

    monkeypatch.setattr(huggingface_hub, "snapshot_download", recorder)
    mod._download(mod.MODELS["small"], tmp_path / "stage")
    assert seen["repo_id"] == "Systran/faster-whisper-small"
    assert seen["revision"] == "536b0662742c02347bc0e980a01041f333bce120"
    assert seen["token"] is False
    assert sorted(seen["allow_patterns"]) == sorted(mod.MODELS["small"].files)


def test_the_real_download_function_is_blocked_by_the_test_network_guard(tmp_path):
    with pytest.raises(Exception):
        mod._download(mod.MODELS["small"], tmp_path / "stage")
    assert NETWORK_ATTEMPTS and set(NETWORK_ATTEMPTS) <= {"huggingface.co"}  # tried only the hub
    assert not any((tmp_path / "stage").rglob("*.bin")) if (tmp_path / "stage").exists() else True


# -- installing ------------------------------------------------------------------------
def test_successful_install_is_atomic_verified_and_recorded(env, monkeypatch, capsys):
    monkeypatch.setattr(mod, "_download", fake_download())
    assert mod.main(["--model", "tiny", "--allow-download"]) == 0
    dest = env / "tiny"
    assert mod.verify_dir(dest, mod.MODELS["tiny"]) == []
    assert not [p for p in env.iterdir() if p.name.startswith(".")]  # no staging leftovers
    import json
    info = json.loads((dest / mod.SOURCE_FILE).read_text())
    assert info["repo"] == "test/repo" and info["revision"] == "a" * 40
    assert info["files"]["model.bin"]["sha256"] == hashlib.sha256(GOOD["model.bin"]).hexdigest()
    assert "Installed and verified" in capsys.readouterr().out


def test_second_run_is_a_no_op_when_already_verified(env, monkeypatch, capsys):
    monkeypatch.setattr(mod, "_download", fake_download())
    mod.main(["--model", "tiny", "--allow-download"])
    forbid_download(monkeypatch)
    assert mod.main(["--model", "tiny", "--allow-download"]) == 0
    assert "Already installed and verified" in capsys.readouterr().out


@pytest.mark.parametrize("content,extra", [
    ({**GOOD, "model.bin": b"corrupted!" * 70}, None),   # same-ish size, wrong content
    ({**GOOD, "config.json": b"{"}, None),               # wrong size
    ({k: v for k, v in GOOD.items() if k != "tokenizer.json"}, None),  # missing file
    (GOOD, {"surprise.bin": b"x"}),                      # unexpected extra file
])
def test_a_failed_verification_installs_nothing_and_cleans_up(env, monkeypatch, capsys, content, extra):
    monkeypatch.setattr(mod, "_download", fake_download(content, extra))
    assert mod.main(["--model", "tiny", "--allow-download"]) == 1
    assert "VERIFICATION FAILED" in capsys.readouterr().out
    assert not (env / "tiny").exists()
    assert not [p for p in env.iterdir()]  # staging folder removed too


def test_a_download_error_installs_nothing_and_reports_only_the_type(env, monkeypatch, capsys):
    def boom(spec, staging):
        staging.mkdir(parents=True)
        (staging / "model.bin").write_bytes(b"partial")
        raise ConnectionError("connection reset while reading https://example/secret-token-abc")

    monkeypatch.setattr(mod, "_download", boom)
    assert mod.main(["--model", "tiny", "--allow-download"]) == 1
    out = capsys.readouterr().out
    assert "FAILED: ConnectionError" in out
    assert not (env / "tiny").exists() and not [p for p in env.iterdir()]


def test_existing_mismatching_folder_is_not_overwritten_without_force(env, monkeypatch, capsys):
    bad = env / "tiny"
    bad.mkdir(parents=True)
    (bad / "config.json").write_bytes(b"mine")
    forbid_download(monkeypatch)
    assert mod.main(["--model", "tiny", "--allow-download"]) == 1
    assert "Use --force" in capsys.readouterr().out
    assert (bad / "config.json").read_bytes() == b"mine"  # untouched


def test_force_replaces_a_mismatching_folder(env, monkeypatch):
    bad = env / "tiny"
    bad.mkdir(parents=True)
    (bad / "old.txt").write_bytes(b"old")
    monkeypatch.setattr(mod, "_download", fake_download())
    assert mod.main(["--model", "tiny", "--allow-download", "--force"]) == 0
    assert mod.verify_dir(bad, mod.MODELS["tiny"]) == [] and not (bad / "old.txt").exists()
    assert not [p for p in env.iterdir() if p.name.startswith(".")]


def test_a_failed_forced_replacement_keeps_the_old_folder(env, monkeypatch):
    bad = env / "tiny"
    bad.mkdir(parents=True)
    (bad / "old.txt").write_bytes(b"old")
    monkeypatch.setattr(mod, "_download", fake_download({**GOOD, "model.bin": b"wrong"}))
    assert mod.main(["--model", "tiny", "--allow-download", "--force"]) == 1
    assert (bad / "old.txt").read_bytes() == b"old"


def test_a_failure_while_swapping_in_the_new_folder_restores_the_previous_one(env, monkeypatch, capsys):
    bad = env / "tiny"
    bad.mkdir(parents=True)
    (bad / "old.txt").write_bytes(b"old")
    monkeypatch.setattr(mod, "_download", fake_download())
    real_replace = mod.os.replace

    def flaky(src, dst):
        if Path(src).name.startswith(".staging"):
            raise OSError("simulated disk error")
        return real_replace(src, dst)

    monkeypatch.setattr(mod.os, "replace", flaky)
    assert mod.main(["--model", "tiny", "--allow-download", "--force"]) == 1
    assert "FAILED: OSError" in capsys.readouterr().out
    assert (bad / "old.txt").read_bytes() == b"old"  # nothing lost
    assert not [p for p in env.iterdir() if p.name.startswith(".")]


def test_not_enough_disk_space_stops_before_any_download(env, monkeypatch, capsys):
    forbid_download(monkeypatch)
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(mod.shutil, "disk_usage", lambda p: usage(10, 9, 1))
    assert mod.main(["--model", "tiny", "--allow-download"]) == 1
    assert "free" in capsys.readouterr().out


# -- verify-only -------------------------------------------------------------------------
def test_verify_only_needs_no_flag_and_no_network(env, monkeypatch, capsys):
    monkeypatch.setattr(mod, "_download", fake_download())
    mod.main(["--model", "tiny", "--allow-download"])
    forbid_download(monkeypatch)
    assert mod.main(["--model", "tiny", "--verify-only"]) == 0
    assert "VERIFIED" in capsys.readouterr().out
    (env / "tiny" / "config.json").write_bytes(b"tampered")
    assert mod.main(["--model", "tiny", "--verify-only"]) == 1
    assert "NOT VERIFIED" in capsys.readouterr().out


def test_verify_only_on_a_missing_install_fails_cleanly(env, monkeypatch):
    forbid_download(monkeypatch)
    assert mod.main(["--model", "tiny", "--verify-only"]) == 1
