#!/usr/bin/env python3
"""Validate the plugin manifests shipped in this repo. Standard library only.

Usage:
  python3 scripts/validate_manifests.py            # structure + version consistency
  python3 scripts/validate_manifests.py --tag v0.2.1  # also require the tag to match
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MCP_URL = "https://www.robowrite.ai/api/mcp"
# Clients name the remote endpoint differently (Gemini CLI uses `httpUrl`).
MCP_URL_KEYS = ("url", "httpUrl", "serverUrl")
REGISTRY_NAME = "ai.robowrite/mcp"
REGISTRY_DESCRIPTION_MAX = 100

# Every file that carries the release version. They must all agree.
VERSIONED = [
    "server.json",
    ".claude-plugin/plugin.json",
    ".codex-plugin/plugin.json",
    ".cursor-plugin/plugin.json",
    ".grok-plugin/plugin.json",
    "gemini-extension.json",
]

# JSON files that must parse, whether or not they carry a version.
JSON_FILES = VERSIONED + [
    ".mcp.json",
    "mcp.json",
    "mcp.codex.json",
    "mcp.grok.json",
    ".agents/plugins/marketplace.json",
]

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
# Anything that looks like a credential has no place in a public plugin repo.
SECRET_KEYS = re.compile(
    r"secret|password|api[_-]?key|private[_-]?key|bearer|"
    r"(?:access|refresh|session|id|auth)[_-]?token|^token$",
    re.I,
)

errors: list[str] = []


def fail(message: str) -> None:
    errors.append(message)


def load(relative: str):
    path = ROOT / relative
    if not path.is_file():
        fail(f"{relative}: missing")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"{relative}: invalid JSON ({exc})")
        return None


def walk(node, relative: str, trail: str = "") -> None:
    """Check every MCP URL and reject credential-looking keys."""
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{trail}.{key}" if trail else key
            if SECRET_KEYS.search(key):
                fail(f"{relative}: credential-like key `{here}`")
            if (
                key in MCP_URL_KEYS
                and isinstance(value, str)
                and value != MCP_URL
                and (here.startswith("mcpServers.") or "/api/mcp" in value)
            ):
                fail(f"{relative}: `{here}` is {value}, expected {MCP_URL}")
            walk(value, relative, here)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            walk(value, relative, f"{trail}[{index}]")


def check_references(relative: str, manifest: dict) -> None:
    """Relative paths named by a plugin manifest must exist."""
    references = [(key, manifest.get(key)) for key in ("mcpServers", "logo", "skills")]
    interface = manifest.get("interface")
    if isinstance(interface, dict):
        references.append(("interface.logo", interface.get("logo")))
    for key, value in references:
        if isinstance(value, str) and not value.startswith(("http://", "https://")):
            if not (ROOT / value).exists():
                fail(f"{relative}: `{key}` points at missing path {value}")


def check_skills() -> None:
    skills = sorted((ROOT / "skills").glob("*/SKILL.md"))
    if not skills:
        fail("skills/: no SKILL.md found")
    for skill in skills:
        relative = skill.relative_to(ROOT).as_posix()
        text = skill.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        if not match:
            fail(f"{relative}: missing YAML frontmatter")
            continue
        fields = dict(
            line.split(":", 1) for line in match.group(1).splitlines() if ":" in line
        )
        name = fields.get("name", "").strip()
        if name != skill.parent.name:
            fail(f"{relative}: frontmatter name `{name}` != directory `{skill.parent.name}`")
        if not fields.get("description", "").strip():
            fail(f"{relative}: frontmatter description is empty")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tag", help="release tag (vX.Y.Z) that every version must match")
    args = parser.parse_args()

    manifests = {relative: load(relative) for relative in JSON_FILES}

    versions: dict[str, str] = {}
    for relative, manifest in manifests.items():
        if manifest is None:
            continue
        walk(manifest, relative)
        if relative in VERSIONED:
            version = manifest.get("version")
            if not isinstance(version, str) or not SEMVER.match(version):
                fail(f"{relative}: version `{version}` is not X.Y.Z")
            else:
                versions[relative] = version
        if relative.endswith("plugin.json"):
            check_references(relative, manifest)

    if len(set(versions.values())) > 1:
        detail = ", ".join(f"{path}={version}" for path, version in versions.items())
        fail(f"version mismatch: {detail}")

    if args.tag:
        expected = args.tag.removeprefix("v")
        for relative, version in versions.items():
            if version != expected:
                fail(f"{relative}: version {version} does not match tag {args.tag}")

    server = manifests.get("server.json")
    if server:
        if server.get("name") != REGISTRY_NAME:
            fail(f"server.json: name must be {REGISTRY_NAME}")
        description = server.get("description", "")
        if not 1 <= len(description) <= REGISTRY_DESCRIPTION_MAX:
            fail(
                f"server.json: description is {len(description)} chars, "
                f"registry allows 1-{REGISTRY_DESCRIPTION_MAX}"
            )
        remotes = [remote.get("url") for remote in server.get("remotes", [])]
        if remotes != [MCP_URL]:
            fail(f"server.json: remotes must be exactly [{MCP_URL}], got {remotes}")

    check_skills()

    if errors:
        for message in errors:
            print(f"::error::{message}" if os.environ.get("GITHUB_ACTIONS") else f"FAIL {message}")
        return 1

    version = next(iter(versions.values()), "?")
    print(f"OK {len(JSON_FILES)} manifests valid, version {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
