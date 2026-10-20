"""Run provenance: yaml_sha and git_head in meta.json are only meaningful when the tree is clean and committed."""
import subprocess
from pathlib import Path


class DirtyTreeError(RuntimeError):
    pass


def git_state(root):
    """(HEAD sha, list of porcelain lines for modified/untracked, non-ignored paths). Raises if git cannot answer."""
    root = str(Path(root))
    try:
        head = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", root, "status", "--porcelain"], capture_output=True, text=True, check=True).stdout.splitlines()
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise DirtyTreeError(f"git state unavailable for {root}: {e}") from e
    return head, dirty


def check_run_provenance(root, smoke):
    """Refuse a non-smoke run on a dirty tree. Returns the HEAD sha."""
    head, dirty = git_state(root)
    if dirty and not smoke:
        raise DirtyTreeError("refusing to run: working tree is not clean/committed (results would not be reproducible):\n  "
                             + "\n  ".join(dirty))
    return head
