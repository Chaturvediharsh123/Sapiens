"""Small git helpers: running git, temporary worktrees, commit info."""
from __future__ import annotations

import contextlib
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


class GitError(RuntimeError):
    pass


def git(repo: Path | str, *args: str, check: bool = True, env: dict | None = None) -> str:
    proc = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True, env=env)
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed:\n{proc.stderr.strip()}")
    return proc.stdout.strip()


def rev_parse(repo: Path, rev: str) -> str:
    return git(repo, "rev-parse", "--verify", f"{rev}^{{commit}}")


def short(sha: str) -> str:
    return sha[:8]


def is_ancestor(repo: Path, older: str, newer: str) -> bool:
    proc = subprocess.run(["git", "merge-base", "--is-ancestor", older, newer],
                          cwd=str(repo), capture_output=True)
    return proc.returncode == 0


def tracked_changes(repo: Path) -> str:
    """Modified tracked files (untracked files are ignored)."""
    return git(repo, "status", "--porcelain", "--untracked-files=no")


def show_file(repo: Path, rev: str, path: str) -> str | None:
    proc = subprocess.run(["git", "show", f"{rev}:{path}"], cwd=str(repo),
                          capture_output=True, text=True)
    return proc.stdout if proc.returncode == 0 else None


def commit_count(repo: Path, rev: str) -> int:
    return int(git(repo, "rev-list", "--count", rev))


def commits_between(repo: Path, good: str, bad: str, paths: list[str] | None = None) -> int:
    args = ["rev-list", "--count", f"{good}..{bad}"]
    if paths:
        args += ["--", *paths]
    return int(git(repo, *args))


@dataclass
class CommitInfo:
    sha: str
    author: str
    date: str
    message: str

    @property
    def short(self) -> str:
        return short(self.sha)


def commit_info(repo: Path, sha: str) -> CommitInfo:
    out = git(repo, "show", "-s", "--format=%H%x1f%an%x1f%ad%x1f%s", "--date=short", sha)
    h, author, date, msg = out.split("\x1f")
    return CommitInfo(h, author, date, msg)


@contextlib.contextmanager
def worktree(repo: Path, rev: str, branch: str | None = None):
    """Check out `rev` into a throwaway worktree so the user's checkout is never touched."""
    path = Path(tempfile.mkdtemp(prefix="culprit-wt-"))
    args = ["worktree", "add", "-q"]
    args += ["-b", branch] if branch else ["--detach"]
    args += [str(path), rev]
    git(repo, *args)
    try:
        yield path
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(path)], cwd=str(repo),
                       capture_output=True)
        shutil.rmtree(path, ignore_errors=True)
        subprocess.run(["git", "worktree", "prune"], cwd=str(repo), capture_output=True)
