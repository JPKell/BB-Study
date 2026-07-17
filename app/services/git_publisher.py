"""Commit and push repository changes using a fixed, non-shell Git workflow."""

from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import threading


class GitPublishError(RuntimeError):
    """Raised when a Git command cannot complete the publish operation."""


class PublishInProgressError(GitPublishError):
    """Raised when another publish operation is already running."""


_publish_lock = threading.Lock()


def _git_executable():
    executable = shutil.which('git')
    if executable:
        return executable
    for candidate in ('/usr/bin/git', '/usr/local/bin/git'):
        if Path(candidate).is_file():
            return candidate
    raise GitPublishError(
        'Git is not installed or is not available to the web application service.'
    )


def _run_git(repository_root, *args):
    try:
        return subprocess.run(
            [_git_executable(), *args],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitPublishError('Git operation timed out.') from exc
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, 'stderr', '') or getattr(exc, 'stdout', '') or str(exc)
        raise GitPublishError(detail.strip() or 'Git operation failed.') from exc


def commit_and_push(repository_root):
    """Stage all changes, create a timestamped commit, and push the current HEAD."""
    root = Path(repository_root).resolve()
    if not _publish_lock.acquire(blocking=False):
        raise PublishInProgressError('A commit and push is already in progress.')

    try:
        _run_git(root, 'rev-parse', '--is-inside-work-tree')
        _run_git(root, 'add', '--all')

        staged = _run_git(root, 'diff', '--cached', '--name-only').stdout.splitlines()
        message = None
        if staged:
            message = f"Update from BB Study ({datetime.now().astimezone():%Y-%m-%d %H:%M:%S %Z})"
            _run_git(root, 'commit', '-m', message)
        commit = _run_git(root, 'rev-parse', '--short', 'HEAD').stdout.strip()
        _run_git(root, 'push', 'origin', 'HEAD')
        return {
            'commit': commit,
            'committed': bool(staged),
            'message': message,
            'files': staged,
        }
    finally:
        _publish_lock.release()
