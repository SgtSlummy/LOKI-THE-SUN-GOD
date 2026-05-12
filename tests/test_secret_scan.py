from __future__ import annotations

from pathlib import Path

import pytest

import scripts.secret_scan as secret_scan


class _FakeRoot:
    def __init__(self, relative_path: Path):
        self.relative_path = relative_path

    def rglob(self, pattern: str):
        assert pattern == "*"
        return [_ExcludedPath(self.relative_path)]


class _ExcludedPath:
    suffix = ""

    def __init__(self, relative_path: Path):
        self.relative_path = relative_path

    def relative_to(self, root):
        return self.relative_path

    def is_file(self):
        raise AssertionError("iter_files should skip excluded directories before stat/is_file")


@pytest.mark.parametrize(
    "relative_path",
    [
        Path(".venv") / "bin" / "python",
        Path("node_modules") / "discord.js" / "src" / "index.js",
        Path("services") / "activity-bridge" / "node_modules" / "discord.js" / "src" / "index.js",
        Path(".env"),
    ],
)
def test_iter_files_skips_excluded_directories_before_stat(monkeypatch, relative_path):
    monkeypatch.setattr(secret_scan, "ROOT", _FakeRoot(relative_path))

    assert secret_scan.iter_files() == []
