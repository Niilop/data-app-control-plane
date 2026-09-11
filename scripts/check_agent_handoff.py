"""Check PR handoff updates using only Git and the Python standard library."""

import argparse
import subprocess
import sys
from pathlib import PurePosixPath

HANDOFF = "mdfiles/next-agent.md"
SECTIONS = (
    "Implemented state",
    "Verification performed",
    "Remaining work and limitations",
    "Next task",
    "Files to read first",
    "Suggested agent prompt",
)


def git(*args: str) -> str:
    """Run Git without shell interpolation; surface invalid/missing refs as errors."""
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True
    ).stdout


def is_documentation(path: str) -> bool:
    """Exempt prose only; unknown file types conservatively require a handoff."""
    file = PurePosixPath(path)
    return file.suffix.lower() in {".md", ".rst"} or file.name in {"LICENSE", "NOTICE"}


def check_handoff(base: str, head: str) -> str:
    """Check the PR's merge-base diff, including deleted and renamed source files."""
    base_commit = git(
        "rev-parse", "--verify", "--end-of-options", f"{base}^{{commit}}"
    ).strip()
    head_commit = git(
        "rev-parse", "--verify", "--end-of-options", f"{head}^{{commit}}"
    ).strip()
    merge_base = git("merge-base", base_commit, head_commit).strip()
    paths = git(
        "diff", "--no-renames", "--name-only", "-z", merge_base, head_commit
    ).split("\0")
    paths = [path for path in paths if path]
    content = git("show", f"{head_commit}:{HANDOFF}")
    missing = [
        section for section in SECTIONS if f"## {section}" not in content.splitlines()
    ]
    if missing:
        raise ValueError(
            f"{HANDOFF} is missing required sections: {', '.join(missing)}"
        )
    if all(is_documentation(path) for path in paths):
        return "Documentation-only PR: no handoff update required."
    if HANDOFF not in paths:
        raise ValueError(
            f"Implementation changes require an update to {HANDOFF} in this PR."
        )
    # A whitespace-only edit should not satisfy the requirement.
    existed = git("ls-tree", "--name-only", merge_base, "--", HANDOFF).strip()
    previous = git("show", f"{merge_base}:{HANDOFF}") if existed else ""
    if "".join(previous.split()) == "".join(content.split()):
        raise ValueError(
            f"Update the content of {HANDOFF}; whitespace-only edits do not count."
        )
    return (
        "Handoff updated. Review its accuracy and verification evidence before merging."
    )


def main() -> int:
    """Return nonzero for missing handoffs, invalid history, or failed Git commands."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()
    try:
        print(check_handoff(args.base, args.head))
    except (ValueError, subprocess.CalledProcessError) as exc:
        detail = (
            exc.stderr.strip()
            if isinstance(exc, subprocess.CalledProcessError)
            else str(exc)
        )
        print(f"Agent handoff check failed: {detail}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
