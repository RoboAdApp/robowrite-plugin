#!/usr/bin/env python3
"""Print the Claude Directory package's Git tree ID for a committed source revision."""

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ".claude-plugin/plugin.json"
LISTING_README = "packaging/claude/README.md"
ROOT_FILES = (MANIFEST, ".mcp.json", "LICENSE", LISTING_README)


def build_tree(repo: Path, revision: str) -> str:
    def git(*args: str, **kwargs) -> bytes:
        return subprocess.run(
            ["git", "--literal-pathspecs", "-C", repo, *args], check=True, stdout=subprocess.PIPE, **kwargs
        ).stdout

    commit = git("rev-parse", "--verify", "--end-of-options", f"{revision}^{{commit}}").decode().strip()
    manifest = json.loads(git("show", f"{commit}:{MANIFEST}"))
    icon = Path(manifest["icon"])
    if icon.parent != Path("assets") or icon.suffix.lower() != ".png":
        raise ValueError("The Claude Directory manifest must point to its approved PNG in assets/")
    required = {*ROOT_FILES, icon.as_posix()}
    records = git("ls-tree", "-r", "-z", commit, "--", *sorted(required), "skills").split(b"\0")
    entries = []
    paths = set()
    for record in filter(None, records):
        header, name = record.split(b"\t", 1)
        mode, kind, oid = header.split()
        if mode != b"100644" or kind != b"blob":
            raise ValueError(f"Claude package files must be regular, non-executable files: {os.fsdecode(name)}")
        paths.add(os.fsdecode(name))
        target = b"README.md" if name == LISTING_README.encode() else name
        entries.append(mode + b" " + oid + b"\t" + target + b"\0")

    missing = required - paths
    if missing:
        raise ValueError("Missing Claude package files: " + ", ".join(sorted(missing)))
    if not any(name.startswith("skills/") and len(Path(name).parts) == 3
               and Path(name).name == "SKILL.md" for name in paths):
        raise ValueError("Missing Claude skill definitions")

    with tempfile.TemporaryDirectory() as temp:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(temp) / "index")}
        git("read-tree", "--empty", env=env)
        git("update-index", "-z", "--index-info", input=b"".join(entries), env=env)
        return git("write-tree", env=env).decode().strip()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("revision", help="Committed package source (for example, HEAD)")
    args = parser.parse_args()
    print(build_tree(ROOT, args.revision))
