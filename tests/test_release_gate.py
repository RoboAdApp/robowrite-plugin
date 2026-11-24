"""Publishing and tagging must be gated on the live connector and managed clients."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"


def parse_jobs(text):
    """Parse the workflow's job graph from YAML structure, ignoring comments.

    Only the constrained subset used by release.yml is needed: job ids, needs,
    if expressions and step run commands. Assertions therefore read the parsed
    job graph, not raw text that a comment could satisfy.
    """
    jobs = {}
    in_jobs = False
    current = None
    key = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        stripped = line.strip()
        if indent == 0:
            in_jobs = stripped == "jobs:"
            current = key = None
            continue
        if not in_jobs:
            continue
        if indent == 2 and re.fullmatch(r"[\w-]+:", stripped):
            current = stripped[:-1]
            jobs[current] = {"needs": [], "if": "", "runs": []}
            key = None
        elif current is None:
            continue
        elif indent == 4:
            match = re.match(r"(needs|if):\s*(.*)$", stripped)
            key = match.group(1) if match else None
            if key == "needs":
                value = match.group(2).strip()
                flow = re.fullmatch(r"\[(.*)\]", value)
                items = flow.group(1).split(",") if flow else [value]
                jobs[current]["needs"] = [item.strip() for item in items if item.strip()]
            elif key == "if":
                jobs[current]["if"] += " " + match.group(2)
        elif indent == 8 and stripped.startswith("run: "):
            jobs[current]["runs"].append(stripped[len("run: "):])
            key = None
        elif indent >= 6 and key == "if":
            jobs[current]["if"] += " " + stripped
        else:
            key = None
    return jobs


class ReleaseGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.jobs = parse_jobs(WORKFLOW.read_text())

    def gate_job(self):
        """Find the job whose steps actually run the strict live smoke gate."""
        for name, job in self.jobs.items():
            if "python3 scripts/smoke_test.py --strict" in job["runs"]:
                return name, job
        self.fail("no job runs the strict live smoke gate")

    def test_publishing_and_tagging_require_the_gate_job(self):
        gate, job = self.gate_job()
        self.assertIn("python3 scripts/validate_manifests.py", job["runs"])
        for name in ("publish-registry", "github-release"):
            self.assertIn(gate, self.jobs[name]["needs"], f"{name} does not depend on {gate}")

    def test_tagging_requires_the_gate_to_succeed(self):
        gate, _ = self.gate_job()
        self.assertIn(f"needs.{gate}.result == 'success'", self.jobs["github-release"]["if"])

    def test_referenced_scripts_exist(self):
        for script in ("scripts/validate_manifests.py", "scripts/smoke_test.py"):
            self.assertTrue((ROOT / script).is_file(), f"missing {script}")
