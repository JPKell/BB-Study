import subprocess
from pathlib import Path

from app.services import git_publisher


def _completed(stdout=''):
    return subprocess.CompletedProcess([], 0, stdout=stdout, stderr='')


def test_commit_and_push_uses_fixed_git_commands(monkeypatch, tmp_path):
    calls = []
    outputs = iter([
        _completed('true\n'),
        _completed(),
        _completed('study.db\napp/example.py\n'),
        _completed(),
        _completed('abc1234\n'),
        _completed(),
    ])

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return next(outputs)

    monkeypatch.setattr(git_publisher.subprocess, 'run', fake_run)
    result = git_publisher.commit_and_push(tmp_path)

    assert [call[0][1:3] for call in calls] == [
        ['rev-parse', '--is-inside-work-tree'],
        ['add', '--all'],
        ['diff', '--cached'],
        ['commit', '-m'],
        ['rev-parse', '--short'],
        ['push', 'origin'],
    ]
    assert Path(calls[-1][0][0]).name == 'git'
    assert calls[-1][0][1:] == ['push', 'origin', 'HEAD']
    assert all(call[1]['cwd'] == tmp_path.resolve() for call in calls)
    assert result['commit'] == 'abc1234'
    assert result['files'] == ['study.db', 'app/example.py']


def test_commit_and_push_still_pushes_when_there_is_no_new_commit(monkeypatch, tmp_path):
    calls = []
    outputs = iter([
        _completed('true\n'), _completed(), _completed(),
        _completed('abc1234\n'), _completed(),
    ])

    def fake_run(command, **kwargs):
        calls.append(command)
        return next(outputs)

    monkeypatch.setattr(git_publisher.subprocess, 'run', fake_run)
    result = git_publisher.commit_and_push(tmp_path)

    assert not any(command[1] == 'commit' for command in calls)
    assert Path(calls[-1][0]).name == 'git'
    assert calls[-1][1:] == ['push', 'origin', 'HEAD']
    assert result['committed'] is False
    assert result['files'] == []
