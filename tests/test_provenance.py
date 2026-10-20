"""Finding 4: a non-smoke run must refuse to start on a dirty git tree."""
import subprocess
from pathlib import Path

import pytest

from provenance import DirtyTreeError, check_run_provenance, git_state


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / ".gitignore").write_text("data/raw/\n")
    (tmp_path / "a.txt").write_text("x\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def test_clean_tree_passes_and_returns_head(repo):
    head = check_run_provenance(repo, smoke=False)
    assert len(head) == 40 and head == git_state(repo)[0]


def test_modified_tracked_file_refuses(repo):
    (repo / "a.txt").write_text("changed\n")
    with pytest.raises(DirtyTreeError, match="a.txt"):
        check_run_provenance(repo, smoke=False)


def test_untracked_file_refuses(repo):
    (repo / "new.csv").write_text("1\n")
    with pytest.raises(DirtyTreeError, match="new.csv"):
        check_run_provenance(repo, smoke=False)


def test_ignored_files_do_not_count(repo):
    (repo / "data" / "raw").mkdir(parents=True)
    (repo / "data" / "raw" / "results.csv").write_text("1\n")
    assert check_run_provenance(repo, smoke=False)


def test_smoke_run_allowed_on_dirty_tree(repo):
    (repo / "a.txt").write_text("changed\n")
    assert check_run_provenance(repo, smoke=True)


def test_not_a_git_repo_fails_loudly(tmp_path):
    with pytest.raises(DirtyTreeError, match="git"):
        check_run_provenance(tmp_path, smoke=False)
