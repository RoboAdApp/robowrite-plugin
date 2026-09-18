#!/usr/bin/env python3
"""Behavior locks for scripts/validate_manifests.py."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "validate_manifests.py"

spec = importlib.util.spec_from_file_location("validate_manifests", SCRIPT)
vm = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(vm)


def walk_errors(node, relative: str = "fixture.json") -> list[str]:
    vm.errors.clear()
    vm.walk(node, relative)
    return list(vm.errors)


class RejectCredentialKeys(unittest.TestCase):
    """Public manifests must not ship token or other credential-looking keys."""

    def test_rejects_token_and_secret_keys(self) -> None:
        keys = (
            "accessToken",
            "refreshToken",
            "sessionToken",
            "idToken",
            "authToken",
            "token",
            "access_token",
            "refresh_token",
            "session_token",
            "id_token",
            "secret",
            "password",
            "api_key",
            "private_key",
            "bearer",
        )
        for key in keys:
            with self.subTest(key=key):
                errors = walk_errors({key: "leak"})
                self.assertTrue(
                    any("credential-like key" in message and key in message for message in errors),
                    errors,
                )

    def test_allows_public_oauth_client_fields(self) -> None:
        errors = walk_errors(
            {
                "url": "https://www.robowrite.ai/api/mcp",
                "clientId": "public-client",
                "CLIENT_ID": "public-client",
                "callbackPort": 8787,
                "scopes": ["user:org:read"],
            }
        )
        self.assertEqual(errors, [])


class CurrentRepoContract(unittest.TestCase):
    def test_shipped_manifests_pass(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OK 10 manifests valid", result.stdout)

    def test_matching_tag_passes_and_wrong_tag_fails(self) -> None:
        vm.errors.clear()
        server = vm.load("server.json")
        self.assertIsInstance(server, dict)
        current = server["version"]
        matching = subprocess.run(
            [sys.executable, str(SCRIPT), "--tag", f"v{current}"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(matching.returncode, 0, matching.stdout + matching.stderr)
        mismatch = subprocess.run(
            [sys.executable, str(SCRIPT), "--tag", "v9.9.9"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(mismatch.returncode, 0)
        self.assertIn("does not match tag v9.9.9", mismatch.stdout)


if __name__ == "__main__":
    unittest.main()
