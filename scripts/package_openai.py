#!/usr/bin/env python3
"""Build a submission ZIP or a separately marked registered-connection preview."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

import validate_manifests as vm

PACKAGE_FILES = (
    ".codex-plugin/plugin.json", "LICENSE", "README.md",
    "assets/robowrite-r.png", "assets/robowrite-r.svg", "mcp.codex.json",
    "skills/robowrite-content-ops/SKILL.md", "skills/robowrite-setup/SKILL.md",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=("submission", "preview"))
    parser.add_argument("--preview-app-id", help="Raw asdk_app_ ID of an authorized private test connection")
    parser.add_argument("--preview-version", help="Private preview revision; does not change the submission version")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.mode != "preview" and (args.preview_app_id or args.preview_version):
        parser.error("private app/version overrides are preview-only")
    if args.preview_app_id and not re.fullmatch(r"asdk_app_[0-9a-f]{32}", args.preview_app_id):
        parser.error("preview app ID must be a raw asdk_app_ identifier")
    if args.preview_version and not vm.SEMVER.fullmatch(args.preview_version):
        parser.error("preview version must use X.Y.Z")
    manifest = json.loads((vm.ROOT / PACKAGE_FILES[0]).read_text())
    registered = json.loads((vm.ROOT / "preview/openai-app.json").read_text())
    vm.check_openai_registered_app(manifest, registered)
    if vm.errors:
        parser.error("; ".join(vm.errors))
    entries = {name: (vm.ROOT / name).read_bytes() for name in PACKAGE_FILES}
    if args.mode == "preview":
        manifest["name"] = "robowrite-preview"
        manifest["interface"]["displayName"] = "RoboWrite Preview"
        if args.preview_version:
            manifest["version"] = args.preview_version
        if args.preview_app_id:
            registered["apps"]["robowrite"]["id"] = args.preview_app_id
        # The browser preview uses the registered connection without also
        # creating a second direct MCP server with a separate login.
        manifest["apps"] = "./.app.json"
        manifest.pop("mcpServers", None)
        # Review cases belong to the URL-based public submission. The local
        # importer rejects plugin-level MCP cases when only an app is mapped.
        extension = manifest.get("extensions", {}).get("com.openai", {})
        extension.pop("review", None)
        extension.pop("publication", None)
        entries[PACKAGE_FILES[0]] = (json.dumps(manifest, indent="\t") + "\n").encode()
        entries[".app.json"] = (json.dumps(registered, indent="\t") + "\n").encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation preserves any earlier pinned package/receipt.
    with zipfile.ZipFile(args.output, "x") as archive:
        for name, content in entries.items():
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content)
    print(json.dumps({
        "mode": args.mode, "output": str(args.output), "entries": len(entries),
        "sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "preview_only_not_for_submission": args.mode == "preview",
    }))


if __name__ == "__main__":
    main()
