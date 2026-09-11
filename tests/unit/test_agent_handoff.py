"""Exercise the checker against real, disposable Git histories."""

import subprocess
import sys
from pathlib import Path

import pytest

CHECKER = Path(__file__).resolve().parents[2] / "scripts/check_agent_handoff.py"
HANDOFF = "mdfiles/next-agent.md"
CONTENT = "\n".join(
    f"## {section}\nRecorded context.\n"
    for section in (
        "Implemented state",
        "Verification performed",
        "Remaining work and limitations",
        "Next task",
        "Files to read first",
        "Suggested agent prompt",
    )
)


def git(repo: Path, *args: str) -> str:
    """Use local identity and no signing/hooks in an isolated test repository."""
    return subprocess.run(
        [
            "git",
            "-c",
            "user.name=Handoff Test",
            "-c",
            "user.email=test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=/dev/null",
            *args,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def write(repo: Path, path: str, content: str) -> None:
    file = repo / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(content)


def commit(repo: Path) -> str:
    git(repo, "add", ".")
    git(repo, "commit", "-m", "Test change")
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, str]:
    git(tmp_path, "init", "-b", "main")
    write(tmp_path, HANDOFF, CONTENT)
    write(tmp_path, "backend/app.py", "original\n")
    return tmp_path, commit(tmp_path)


def check(repo: Path, base: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER), "--base", base, "--head", "HEAD"],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=10,
    )


@pytest.mark.parametrize(
    "path",
    [
        "backend/app.py",
        "tests/test_new.py",
        "uv.lock",
        "backend/requirements.txt",
        "Dockerfile",
        ".github/workflows/ci.yml",
        "scripts/tool.sh",
        "new\nfile.py",
    ],
)
def test_implementation_requires_handoff(repo: tuple[Path, str], path: str) -> None:
    directory, base = repo
    write(directory, path, "changed\n")
    commit(directory)
    result = check(directory, base)
    assert result.returncode == 1
    assert "require an update" in result.stderr


def test_documentation_only_is_exempt(repo: tuple[Path, str]) -> None:
    directory, base = repo
    write(directory, "README.md", "Documentation change\n")
    commit(directory)
    assert check(directory, base).returncode == 0


def test_implementation_with_handoff_passes(repo: tuple[Path, str]) -> None:
    directory, base = repo
    write(directory, "backend/app.py", "changed\n")
    write(
        directory,
        HANDOFF,
        CONTENT.replace("Recorded context.", "Updated behavior and evidence."),
    )
    commit(directory)
    assert check(directory, base).returncode == 0


@pytest.mark.parametrize(
    "change", ["delete", "rename", "whitespace", "missing_section"]
)
def test_invalid_handoff_fails(repo: tuple[Path, str], change: str) -> None:
    directory, base = repo
    write(directory, "backend/app.py", "changed\n")
    if change == "delete":
        (directory / HANDOFF).unlink()
    elif change == "rename":
        (directory / HANDOFF).rename(directory / "mdfiles/old-handoff.md")
    elif change == "whitespace":
        write(directory, HANDOFF, CONTENT + "\n\n")
    else:
        write(directory, HANDOFF, CONTENT.replace("## Next task", "## Old task"))
    commit(directory)
    assert check(directory, base).returncode == 1


@pytest.mark.parametrize("rename", [False, True])
def test_removed_or_renamed_source_requires_handoff(
    repo: tuple[Path, str], rename: bool
) -> None:
    directory, base = repo
    file = directory / "backend/app.py"
    if rename:
        file.rename(directory / "backend/app.md")
    else:
        file.unlink()
    commit(directory)
    assert check(directory, base).returncode == 1


def test_base_only_handoff_change_does_not_count(repo: tuple[Path, str]) -> None:
    directory, fork = repo
    write(directory, HANDOFF, CONTENT + "Base branch update.\n")
    base = commit(directory)
    git(directory, "checkout", "-b", "feature", fork)
    write(directory, "backend/app.py", "changed\n")
    commit(directory)
    result = check(directory, base)
    assert result.returncode == 1
    assert "require an update" in result.stderr


def test_missing_history_fails(repo: tuple[Path, str]) -> None:
    directory, _ = repo
    assert check(directory, "nonexistent-base").returncode == 1
