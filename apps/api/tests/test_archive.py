import gzip
import io
import tarfile
from pathlib import Path

import pytest

from codeatlas.core.errors import DomainError
from codeatlas.ingestion.archive import ScanLimits, safe_member_path, scan_archive
from codeatlas.ingestion.runner import analyze


def make_archive(path: Path, files: dict[str, bytes], *, special: tarfile.TarInfo | None = None):
    with tarfile.open(path, "w:gz") as archive:
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
        if special:
            archive.addfile(special)
    return path


@pytest.mark.parametrize(
    "path",
    [
        "../outside.py",
        "/tmp/a",
        "repo/../a",
        "repo//a",
        "repo/./a",
        "repo\\a",
        "repo/C:/a",
        "repo/a\n.py",
    ],
)
def test_rejects_unsafe_paths(path):
    with pytest.raises(DomainError, match="unsafe path"):
        safe_member_path(path)


@pytest.mark.parametrize(
    "kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE]
)
def test_rejects_links_and_special_entries(tmp_path, kind):
    special = tarfile.TarInfo("repo/evil")
    special.type = kind
    special.linkname = "/etc/passwd"
    archive = make_archive(tmp_path / "repository.tar.gz", {}, special=special)
    with pytest.raises(DomainError, match="links"):
        scan_archive(archive, tmp_path, ScanLimits())


def test_scanning_skips_and_partial_failure(tmp_path):
    archive = make_archive(
        tmp_path / "repository.tar.gz",
        {
            "repo/src/main.py": b"def hello(name): return name",
            "repo/src/broken.py": b"def broken(:",
            "repo/node_modules/module/a.js": b"function ignored() {}",
            "repo/.venv/a.py": b"def ignored(): pass",
            "repo/README.md": b"read me",
            "repo/binary.py": b"\x00\xff",
            "repo/latin.py": b"\xff",
            "repo/generated.py": b"# @generated\ndef ignored(): pass",
            "repo/types.d.ts": b"declare const x: number;",
        },
    )
    result = scan_archive(archive, tmp_path, ScanLimits())
    assert [f.path for f in result.files] == ["src/broken.py", "src/main.py"]
    assert result.files[0].parsed.warning
    assert result.skipped == {
        "ignored_directory": 2,
        "unsupported_type": 1,
        "binary_file": 1,
        "unsupported_encoding": 1,
        "generated_file": 2,
    }
    assert not (tmp_path / "src").exists()


def test_expansion_bomb_is_bounded_before_tar_parsing(tmp_path):
    archive = tmp_path / "repository.tar.gz"
    archive.write_bytes(gzip.compress(b"\0" * 100_000))
    with pytest.raises(DomainError, match="Expanded archive"):
        scan_archive(archive, tmp_path, ScanLimits(max_expanded_bytes=1000))


@pytest.mark.parametrize(
    "limits, message",
    [
        (ScanLimits(max_entries=1), "too many entries"),
        (ScanLimits(max_source_bytes=5), "storage limit"),
        (ScanLimits(max_symbols=1), "too many symbols"),
    ],
)
def test_repository_limits(tmp_path, limits, message):
    archive = make_archive(
        tmp_path / "repository.tar.gz",
        {
            "repo/a.py": b"def one(): pass",
            "repo/b.py": b"def two(): pass",
        },
    )
    with pytest.raises(DomainError, match=message):
        scan_archive(archive, tmp_path, limits)


def test_large_files_are_skipped(tmp_path):
    archive = make_archive(tmp_path / "repository.tar.gz", {"repo/a.py": b"x" * 30})
    result = scan_archive(archive, tmp_path, ScanLimits(max_file_bytes=10))
    assert result.skipped == {"oversized_file": 1}
    assert not result.files


def test_case_collisions_are_rejected(tmp_path):
    archive = make_archive(tmp_path / "repository.tar.gz", {"repo/A.py": b"", "repo/a.py": b""})
    with pytest.raises(DomainError, match="duplicate"):
        scan_archive(archive, tmp_path, ScanLimits())


def test_corrupt_archive(tmp_path):
    archive = tmp_path / "repository.tar.gz"
    archive.write_bytes(b"not gzip")
    with pytest.raises(DomainError, match="malformed"):
        scan_archive(archive, tmp_path, ScanLimits())


def test_real_isolated_parser_worker(tmp_path):
    make_archive(tmp_path / "repository.tar.gz", {"repo/real.py": b"def real(): pass"})
    result = analyze(tmp_path, ScanLimits(), 10)
    assert result.files[0].parsed.symbols[0].name == "real"


def test_worker_timeout_is_controlled(tmp_path, monkeypatch):
    import subprocess

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("trusted-parser", 1)

    monkeypatch.setattr("codeatlas.ingestion.runner.subprocess.run", timeout)
    with pytest.raises(DomainError, match="time limit"):
        analyze(tmp_path, ScanLimits(), 1)


def test_captures_bounded_alias_config_separately_from_source(tmp_path):
    archive = make_archive(
        tmp_path / "repository.tar.gz",
        {
            "repo/web/tsconfig.json": b'{"compilerOptions":{"paths":{"@/*":["src/*"]}}}',
            "repo/web/src/a.ts": b"import '@/b';",
            "repo/node_modules/tsconfig.json": b"ignored",
        },
    )
    result = scan_archive(archive, tmp_path, ScanLimits())
    assert len(result.files) == 1
    assert result.resolution_configs[0].paths == {"@/*": ["src/*"]}
    assert result.skipped == {"resolution_config": 1, "ignored_directory": 1}


def test_import_observation_limit(tmp_path):
    archive = make_archive(tmp_path / "repository.tar.gz", {"repo/a.py": b"import os\nimport sys"})
    with pytest.raises(DomainError, match="too many import"):
        scan_archive(archive, tmp_path, ScanLimits(max_imports=1))
