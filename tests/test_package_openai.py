"""The registered preview must never leak into the public submission archive."""

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class OpenAIPackageBoundary(unittest.TestCase):
    def test_private_connection_and_revision_overrides_cannot_enter_submission(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "submission.zip"
            for option, value in (
                ("--preview-app-id", "asdk_app_00000000000000000000000000000001"),
                ("--preview-version", "0.3.1"),
            ):
                result = subprocess.run(
                    [sys.executable, str(ROOT / "scripts/package_openai.py"),
                     "--mode", "submission", option, value, str(target)],
                    capture_output=True, text=True, check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("preview-only", result.stderr)
                self.assertFalse(target.exists())

    def test_private_preview_override_changes_only_its_connection_and_revision(self) -> None:
        app_id = "asdk_app_00000000000000000000000000000001"
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "preview.zip"
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/package_openai.py"),
                 "--mode", "preview", "--preview-app-id", app_id,
                 "--preview-version", "0.3.1", str(target)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with zipfile.ZipFile(target) as archive:
                manifest = json.loads(archive.read(".codex-plugin/plugin.json"))
                self.assertEqual(manifest["version"], "0.3.1")
                self.assertEqual(json.loads(archive.read(".app.json"))["apps"]["robowrite"]["id"], app_id)
                for name in archive.namelist():
                    if name not in {".codex-plugin/plugin.json", ".app.json"}:
                        self.assertEqual(archive.read(name), (ROOT / name).read_bytes())

    def test_submission_and_preview_preserve_content_but_use_distinct_connections(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            archives = {}
            for mode in ("submission", "preview"):
                target = Path(temporary) / f"{mode}.zip"
                result = subprocess.run(
                    [sys.executable, str(ROOT / "scripts/package_openai.py"),
                     "--mode", mode, str(target)],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                with zipfile.ZipFile(target) as archive:
                    archives[mode] = {name: archive.read(name) for name in archive.namelist()}
            submission, preview = archives["submission"], archives["preview"]
            self.assertNotIn(".app.json", submission)
            release_manifest = json.loads(submission[".codex-plugin/plugin.json"])
            preview_manifest = json.loads(preview[".codex-plugin/plugin.json"])
            self.assertNotIn("apps", release_manifest)
            self.assertEqual(release_manifest["name"], "robowrite")
            self.assertEqual(preview_manifest["name"], "robowrite-preview")
            self.assertEqual(preview_manifest["interface"]["displayName"], "RoboWrite Preview")
            self.assertEqual(release_manifest["mcpServers"], "./mcp.codex.json")
            self.assertEqual(preview_manifest["apps"], "./.app.json")
            self.assertNotIn("mcpServers", preview_manifest)
            self.assertIn("test_cases", release_manifest["extensions"]["com.openai"]["review"])
            self.assertNotIn("review", preview_manifest["extensions"]["com.openai"])
            self.assertNotIn("publication", preview_manifest["extensions"]["com.openai"])
            for name in submission.keys() - {".codex-plugin/plugin.json"}:
                self.assertEqual(submission[name], preview[name], name)
                self.assertEqual(submission[name], (ROOT / name).read_bytes(), name)
            expected = json.loads((ROOT / "preview/openai-app.json").read_text())
            self.assertEqual(json.loads(preview[".app.json"]), expected)


if __name__ == "__main__":
    unittest.main()
