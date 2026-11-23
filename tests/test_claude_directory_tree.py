import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from claude_directory_tree import build_tree


class ClaudeDirectoryTreeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git("init", "--quiet")
        self.files = {
            ".claude-plugin/plugin.json": '{"icon":"./assets/logo.png"}',
            ".mcp.json": "connection",
            "assets/logo.png": "logo",
            "LICENSE": "license",
            "packaging/claude/README.md": "listing",
            "skills/setup/SKILL.md": "setup",
            "skills/setup/references/usage.md": "supporting file",
        }
        for name, content in {
            **self.files, "README.md": "maintainer docs", "assets/extra.svg": "other icon",
        }.items():
            dest = self.repo / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content)
        self.git("add", ".")
        self.commit()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", self.repo, *args])

    def commit(self):
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "-c", "commit.gpgSign=false", "commit", "--quiet", "-m", "fixture")

    def test_projects_committed_files_and_preserves_staged_work(self):
        (self.repo / "skills/setup/SKILL.md").write_text("unreleased edit")
        self.git("add", "skills/setup/SKILL.md")
        index = self.git("write-tree")
        tree = build_tree(self.repo, "HEAD")
        self.assertEqual(tree, build_tree(self.repo, "HEAD"))
        self.assertEqual(index, self.git("write-tree"))
        expected = dict(self.files)
        expected["README.md"] = expected.pop("packaging/claude/README.md")
        names = self.git("ls-tree", "-r", "--name-only", tree).decode().splitlines()
        self.assertEqual(set(names), set(expected))
        for name, content in expected.items():
            self.assertEqual(self.git("show", f"{tree}:{name}"), content.encode())

    def test_refuses_a_missing_declared_icon(self):
        self.git("rm", "--quiet", "assets/logo.png")
        self.commit()
        with self.assertRaisesRegex(ValueError, "assets/logo.png"):
            build_tree(self.repo, "HEAD")

    def test_refuses_links_in_skills(self):
        (self.repo / "skills/setup/reference").symlink_to("../../README.md")
        self.git("add", ".")
        self.commit()
        with self.assertRaisesRegex(ValueError, "skills/setup/reference"):
            build_tree(self.repo, "HEAD")
