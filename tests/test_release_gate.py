"""Publishing must be gated on the live connector and managed-client sign-in."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReleaseGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text()

    def job_body(self, name):
        match = re.search(rf"^  {name}:\n(?P<body>(?:    .*\n|\n)*)", self.workflow, re.M)
        self.assertIsNotNone(match, f"release.yml has no {name} job")
        return match.group("body")

    def test_release_gate_runs_manifest_validation_and_strict_live_smoke(self):
        body = self.job_body("release-gate")
        self.assertIn("python3 scripts/validate_manifests.py", body)
        self.assertIn("python3 scripts/smoke_test.py --strict", body)

    def test_publishing_depends_on_the_release_gate(self):
        needs = re.search(r"^    needs: (.+)$", self.job_body("publish-registry"), re.M)
        self.assertIsNotNone(needs, "publish-registry has no needs clause")
        self.assertIn("release-gate", needs.group(1))

    def test_referenced_scripts_exist(self):
        for script in ("scripts/validate_manifests.py", "scripts/smoke_test.py"):
            self.assertTrue((ROOT / script).is_file(), f"missing {script}")
