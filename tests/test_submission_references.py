"""Exercise the release entry points with broken references in a package copy."""

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class GrokManualInstallation(unittest.TestCase):
    @unittest.skipUnless(sys.version_info >= (3, 11), "requires standard-library TOML parser")
    def test_documented_toml_matches_the_packaged_connection(self):
        import tomllib

        readme = (ROOT / "README.md").read_text()
        example, = re.findall(r"^```toml\n(\[mcp_servers\.robowrite\]\n.*?)^```$", readme, re.M | re.S)
        documented = tomllib.loads(example)["mcp_servers"]["robowrite"]
        packaged = json.loads((ROOT / "mcp.grok.json").read_text())["mcpServers"]["robowrite"]
        for key in ("url", "oauth_client_id", "oauth_scopes"):
            self.assertEqual(documented[key], packaged[key])


class SubmissionReferences(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        # Copy the package inputs without the checkout, build products or test profiles.
        sources = [
            *ROOT.glob("*.json"),
            *ROOT.glob(".*-plugin"),
            *(ROOT / name for name in (".agents", "assets", "preview", "skills", "scripts", "README.md", "LICENSE")),
        ]
        for source in sources:
            target = self.root / source.name
            if source.is_dir():
                shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
            else:
                shutil.copyfile(source, target)

    def run_tool(self, name, *args):
        return subprocess.run(
            [sys.executable, self.root / "scripts" / name, *args],
            capture_output=True, text=True, check=False,
        )

    def test_submission_requires_the_packaged_connection(self):
        path = self.root / ".codex-plugin/plugin.json"
        manifest = json.loads(path.read_text())
        del manifest["mcpServers"]
        output = self.root / "submission.zip"
        for source in [manifest, {**manifest, "mcpServers": "./mcp.json"}]:
            with self.subTest(source=source.get("mcpServers")):
                path.write_text(json.dumps(source))
                results = [
                    self.run_tool("validate_manifests.py"),
                    self.run_tool("package_openai.py", "--mode", "submission", output),
                ]
                for result in results:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("mcpServers must reference ./mcp.codex.json", result.stdout + result.stderr)
                self.assertFalse(output.exists())

    def test_claude_requires_its_declared_icon_in_the_package(self):
        path = self.root / ".claude-plugin/plugin.json"
        manifest = json.loads(path.read_text())
        del manifest["icon"]
        (self.root / "assets/linked.png").symlink_to("robowrite-r.png")
        for icon in [None, "./assets/missing.png", "./assets/robowrite-r.svg", "./assets/linked.png"]:
            with self.subTest(icon=icon):
                path.write_text(json.dumps(manifest if icon is None else {**manifest, "icon": icon}))
                result = self.run_tool("validate_manifests.py")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(".claude-plugin/plugin.json: icon", result.stdout)
