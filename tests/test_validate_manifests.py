#!/usr/bin/env python3
"""Behavior locks for scripts/validate_manifests.py."""

from __future__ import annotations

import copy
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
                "url": "https://mcp.robowrite.ai/mcp",
                "clientId": "public-client",
                "CLIENT_ID": "public-client",
                "callbackPort": 8787,
                "scopes": ["user:org:read"],
            }
        )
        self.assertEqual(errors, [])

    def test_rejects_mcp_server_url_that_is_not_the_hosted_endpoint(self) -> None:
        errors = walk_errors(
            {"mcpServers": {"robowrite": {"url": "https://evil.example/other"}}}
        )
        self.assertTrue(
            any("https://evil.example/other" in message and "expected" in message for message in errors),
            errors,
        )

    def test_rejects_wrong_endpoint_under_client_specific_url_keys(self) -> None:
        for key in ("httpUrl", "serverUrl"):
            errors = walk_errors(
                {"mcpServers": {"robowrite": {key: "https://evil.example/other"}}}
            )
            self.assertTrue(any("expected" in message for message in errors), (key, errors))

    def test_allows_unrelated_url_fields(self) -> None:
        errors = walk_errors(
            {
                "author": {"url": "https://www.robowrite.ai"},
                "repository": {"url": "https://github.com/RoboAdApp/robowrite-plugin"},
            }
        )
        self.assertEqual(errors, [])

    def test_rejects_missing_nested_interface_logo(self) -> None:
        vm.errors.clear()
        vm.check_references(
            ".codex-plugin/plugin.json",
            {"interface": {"logo": "./missing-codex-logo.png"}},
        )
        self.assertTrue(any("interface.logo" in message for message in vm.errors), vm.errors)


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
        self.assertIn("OK 11 manifests valid", result.stdout)

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


class OpenAIDirectoryMetadata(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = vm.load(".codex-plugin/plugin.json")
        vm.errors.clear()

    def validate(self, manifest: dict) -> list[str]:
        vm.errors.clear()
        vm.check_openai_metadata(".codex-plugin/plugin.json", manifest)
        return list(vm.errors)

    def test_shipped_metadata_and_explicit_mcp_path_are_valid(self) -> None:
        self.assertEqual(self.validate(self.manifest), [])
        self.assertTrue((ROOT / self.manifest["mcpServers"]).is_file())

    def test_required_listing_text_and_urls_cannot_be_omitted(self) -> None:
        for key in (*vm.OPENAI_TEXT_LIMITS, *vm.OPENAI_LISTING_URLS):
            with self.subTest(key=key):
                manifest = copy.deepcopy(self.manifest)
                manifest["interface"].pop(key)
                self.assertTrue(self.validate(manifest))

    def test_directory_subtitle_boundary_is_thirty_characters(self) -> None:
        self.manifest["interface"]["shortDescription"] = "x" * 30
        self.assertEqual(self.validate(self.manifest), [])
        self.manifest["interface"]["shortDescription"] += "x"
        self.assertTrue(self.validate(self.manifest))

    def test_public_policy_urls_cannot_contain_credentials_or_use_http(self) -> None:
        for url in ("http://example.com/terms", "https://user:password@example.com/terms", "not-a-url"):
            with self.subTest(url=url):
                self.manifest["interface"]["termsOfServiceURL"] = url
                self.assertTrue(self.validate(self.manifest))

    def test_capabilities_accept_empty_list_and_reject_invalid_labels(self) -> None:
        self.manifest["interface"]["capabilities"] = []
        self.assertEqual(self.validate(self.manifest), [])
        for value in (None, "Read", [" "], ["x" * 121], ["Read"] * 21):
            with self.subTest(value=value):
                self.manifest["interface"]["capabilities"] = value
                self.assertTrue(self.validate(self.manifest))

    def test_composer_icon_must_be_an_included_asset(self) -> None:
        for value in (None, "./missing.png", "../README.md", "https://example.com/icon.png"):
            with self.subTest(value=value):
                self.manifest["interface"]["composerIcon"] = value
                self.assertTrue(self.validate(self.manifest))

    def test_starter_prompt_count_and_length_limits(self) -> None:
        self.manifest["interface"]["defaultPrompt"] = "x" * 128
        self.assertEqual(self.validate(self.manifest), [])
        for value in ("x" * 129, ["prompt"] * 4):
            with self.subTest(value=value):
                self.manifest["interface"]["defaultPrompt"] = value
                self.assertTrue(self.validate(self.manifest))

    def test_setup_entry_must_reference_an_included_skill(self) -> None:
        self.manifest["extensions"]["com.openai"]["onboardingSkill"] = "./README.md"
        self.assertTrue(self.validate(self.manifest))


if __name__ == "__main__":
    unittest.main()
