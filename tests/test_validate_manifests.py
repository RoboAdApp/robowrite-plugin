#!/usr/bin/env python3
"""Behavior locks for scripts/validate_manifests.py."""

from __future__ import annotations

import copy
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
        for url in ("http://example.com/terms", "https://user:password@example.com/terms", "not-a-url", "https://example.com:invalid/terms", "https://example.com:99999/terms"):
            with self.subTest(url=url):
                self.manifest["interface"]["termsOfServiceURL"] = url
                self.assertTrue(self.validate(self.manifest))
        self.manifest["interface"]["termsOfServiceURL"] = "https://example.com:443/terms"
        self.assertEqual(self.validate(self.manifest), [])

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

    def test_icon_paths_reject_parent_segments_even_when_resolution_stays_inside(self) -> None:
        for key in ("logo", "composerIcon", "logoDark", "composerIconDark"):
            with self.subTest(key=key):
                manifest = copy.deepcopy(self.manifest)
                manifest["interface"][key] = "./assets/../assets/robowrite-r.svg"
                self.assertTrue(self.validate(manifest))

    def test_starter_prompt_count_and_length_limits(self) -> None:
        self.manifest["interface"]["defaultPrompt"] = "x" * 128
        self.assertEqual(self.validate(self.manifest), [])
        for value in ("x" * 129, ["Read my account", "List my drafts", "Find my brief", "Read my review"]):
            with self.subTest(value=value):
                self.manifest["interface"]["defaultPrompt"] = value
                self.assertIn(".codex-plugin/plugin.json: interface.defaultPrompt allows up to three nonempty prompts of 128 characters", self.validate(self.manifest))

    def test_required_and_supplied_optional_icons_respect_five_mib_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            references = {self.manifest["interface"][key] for key in vm.OPENAI_REQUIRED_ICONS}
            references.add(self.manifest["extensions"]["com.openai"]["onboardingSkill"])
            for value in references:
                target = root / value
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / value).read_bytes())
            asset = root / "boundary.png"
            asset.write_bytes((ROOT / self.manifest["interface"]["composerIcon"]).read_bytes())
            for key in (*vm.OPENAI_REQUIRED_ICONS, *vm.OPENAI_OPTIONAL_ICONS):
                with self.subTest(key=key), mock.patch.object(vm, "ROOT", root):
                    # Preserve a real PNG prefix; pad only a disposable copy.
                    with asset.open("r+b") as stream:
                        stream.truncate(vm.OPENAI_ICON_MAX_BYTES)
                    manifest = copy.deepcopy(self.manifest)
                    manifest["interface"][key] = "./boundary.png"
                    self.assertEqual(self.validate(manifest), [])
                    with asset.open("r+b") as stream:
                        stream.truncate(vm.OPENAI_ICON_MAX_BYTES + 1)
                    self.assertEqual(self.validate(manifest), [f".codex-plugin/plugin.json: interface.{key} must not exceed 5 MiB"])

    def test_setup_entry_must_reference_an_included_skill(self) -> None:
        self.manifest["extensions"]["com.openai"]["onboardingSkill"] = "./README.md"
        self.assertTrue(self.validate(self.manifest))

    def test_setup_entry_requires_a_direct_skill_directory_even_when_nested_file_exists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for value in {self.manifest["interface"][key] for key in vm.OPENAI_REQUIRED_ICONS}:
                asset = root / value
                asset.parent.mkdir(parents=True, exist_ok=True)
                asset.write_bytes((ROOT / value).read_bytes())
            for relative, accepted in (("./skills/setup/SKILL.md", True), ("./skills/group/setup/SKILL.md", False)):
                with self.subTest(relative=relative):
                    skill = root / relative
                    skill.parent.mkdir(parents=True, exist_ok=True)
                    skill.write_text("---\nname: setup\ndescription: Setup\n---\nSetup workflow\n")
                    self.manifest["extensions"]["com.openai"]["onboardingSkill"] = relative
                    with mock.patch.object(vm, "ROOT", root):
                        errors = self.validate(self.manifest)
                    self.assertEqual(errors, [] if accepted else [".codex-plugin/plugin.json: onboardingSkill must reference an included skill"])

    def test_required_text_needs_content_but_keeps_format_characters_with_visible_text(self) -> None:
        for key in ("displayName", "shortDescription", "longDescription", "developerName", "capabilities", "defaultPrompt"):
            for content in ("\u200b", " \u200c\u200d\u2060 "):
                with self.subTest(key=key, content=content):
                    manifest = copy.deepcopy(self.manifest)
                    manifest["interface"][key] = [content] if key in ("capabilities", "defaultPrompt") else content
                    self.assertTrue(self.validate(manifest))
            manifest = copy.deepcopy(self.manifest)
            manifest["interface"][key] = ["Team 👩\u200d💻"] if key in ("capabilities", "defaultPrompt") else "مهدی\u200cزاره"
            self.assertEqual(self.validate(manifest), [])

    def test_listing_urls_allow_fragments_without_relaxing_other_url_rules(self) -> None:
        for key in vm.OPENAI_LISTING_URLS:
            with self.subTest(key=key):
                self.manifest["interface"][key] = "https://example.com/privacy?lang=en#choices"
                self.assertEqual(self.validate(self.manifest), [])
                self.manifest["interface"][key] = "https://example.com/privacy#bad\nfragment"
                self.assertTrue(self.validate(self.manifest))
                self.manifest["interface"][key] = "https://example.com/privacy#choices"

    def test_category_uses_supported_directory_titles(self) -> None:
        for category in ("Writing", "productivity"):
            with self.subTest(category=category):
                self.manifest["interface"]["category"] = category
                self.assertTrue(self.validate(self.manifest))
        for category in ("Productivity", "Business & Operations", "Other"):
            self.manifest["interface"]["category"] = category
            self.assertEqual(self.validate(self.manifest), [])

    def test_optional_dark_icons_stay_optional_and_must_be_included_when_present(self) -> None:
        self.assertEqual(self.validate(self.manifest), [])
        for key in ("logoDark", "composerIconDark"):
            for value in ("https://example.com/icon.svg", "./missing.svg", "../icon.svg", "./README.md", None):
                with self.subTest(key=key, value=value):
                    manifest = copy.deepcopy(self.manifest)
                    manifest["interface"][key] = value
                    self.assertTrue(self.validate(manifest))
            self.manifest["interface"][key] = self.manifest["interface"]["logo"]
        self.assertEqual(self.validate(self.manifest), [])

    def test_single_line_fields_reject_line_breaks_but_description_allows_them(self) -> None:
        for key in ("displayName", "shortDescription", "developerName"):
            for separator in ("\n", "\r\n", "\u2028", "\x85"):
                with self.subTest(key=key, separator=separator):
                    manifest = copy.deepcopy(self.manifest)
                    manifest["interface"][key] = "Plan" + separator + "content"
                    self.assertTrue(self.validate(manifest))
        self.manifest["interface"]["longDescription"] = "Plan\ncontent"
        self.assertEqual(self.validate(self.manifest), [])

    def test_starter_prompts_reject_unicode_and_whitespace_equivalent_duplicates(self) -> None:
        for prompts in (["Check my account", "Check  my\u00a0account"], ["Caf\u00e9 drafts", "Cafe\u0301 drafts"], ["Plan content", "\uff30lan content"]):
            with self.subTest(prompts=prompts):
                self.manifest["interface"]["defaultPrompt"] = prompts
                self.assertTrue(self.validate(self.manifest))
        self.manifest["interface"]["defaultPrompt"] = ["Check my account", "Read a brief"]
        self.assertEqual(self.validate(self.manifest), [])

    def test_capabilities_and_prompts_must_also_fit_one_line(self) -> None:
        for key in ("capabilities", "defaultPrompt"):
            with self.subTest(key=key):
                manifest = copy.deepcopy(self.manifest)
                manifest["interface"][key] = ["Plan\ncontent"]
                self.assertTrue(self.validate(manifest))

    def test_listing_controls_fail_without_rejecting_unicode_or_description_newlines(self) -> None:
        for key in ("displayName", "shortDescription", "longDescription", "developerName", "capabilities", "defaultPrompt"):
            for control in ("\t", "\x00", "\x7f", "\x85", "\ud800", "\u2028", "\u2029"):
                with self.subTest(key=key, control=control):
                    manifest = copy.deepcopy(self.manifest)
                    text = "Plan" + control + "content"
                    manifest["interface"][key] = [text] if key in ("capabilities", "defaultPrompt") else text
                    self.assertTrue(self.validate(manifest))
        self.manifest["interface"]["developerName"] = "مهدی\u200cزاره"
        self.manifest["interface"]["longDescription"] = "Caf\u00e9 content\r\nفناوری\nTeam 👩\u200d💻"
        self.manifest["interface"]["defaultPrompt"] = ["Read the café brief"]
        self.assertEqual(self.validate(self.manifest), [])

    def test_url_hosts_preserve_valid_forms_and_reject_raw_or_escaped_invalid_characters(self) -> None:
        valid = (
            "https://bücher.example/terms", "https://xn--bcher-kva.example/terms",
            "https://192.0.2.1:443/terms", "https://[2001:db8::1]:443/terms",
            "https://%65xample.com/terms", "https://example.com./terms",
            "https://service_name.example/terms", "https://example.com/terms%20and%20conditions",
        )
        invalid = (
            "https://exa mple.com/terms", "https://exa\tmple.com/terms",
            "https://example.com/te\nrms", "https://exa%20mple.com/terms",
            "https://exa%0ample.com/terms", "https://exa%2fmple.com/terms",
            "https://exa|mple.com/terms", "https://exa{mple.com/terms",
            "https://exa%mple.com/terms", "https://%ff.example/terms",
        )
        for url in valid:
            with self.subTest(valid=url):
                self.manifest["interface"]["termsOfServiceURL"] = url
                self.assertEqual(self.validate(self.manifest), [])
        for url in invalid:
            with self.subTest(invalid=url):
                self.manifest["interface"]["termsOfServiceURL"] = url
                self.assertTrue(self.validate(self.manifest))

    def test_starter_mentions_fail_but_emails_and_ordinary_at_symbols_remain_valid(self) -> None:
        for prompt in (
            "@robowrite show my drafts", "Open (@robowrite) and read my brief",
            "Read https://example.com/@author then @robowrite show my drafts",
            "Read [https://example.com/@author]@robowrite",
            "Read [notes](https://example.com/@author)@robowrite",
            "Read <https://example.com/@author>@robowrite",
            "Read `https://example.com/@author`@robowrite",
            'Read "https://example.com/@author"@robowrite',
            "Read 'https://example.com/@author'@robowrite",
            "Read https://exa%20mple.com/@robowrite",
            "Read https://example.com:invalid/@robowrite",
        ):
            with self.subTest(prompt=prompt):
                self.manifest["interface"]["defaultPrompt"] = [prompt]
                self.assertTrue(self.validate(self.manifest))
        for prompt in (
            "Find the brief for writer@example.com", "Explain the @ symbol", "Read my café draft",
            "Read https://example.com/@author", "Read https://example.com/?writer=@author",
            "Read https://example.com/#@author", "Read http://[2001:db8::1]/@author",
            "Read HTTPS://example.com/@author", "Read HTTP://example.com/?writer=@author",
            "Read `https://example.com/@author`",
            'Read "https://example.com/@author"', "Read 'https://example.com/@author'",
            "Read https://example.com/O'Reilly/@author",
            "Read https://example.com/?name=O'Reilly&writer=@author",
        ):
            with self.subTest(prompt=prompt):
                self.manifest["interface"]["defaultPrompt"] = [prompt]
                self.assertEqual(self.validate(self.manifest), [])


if __name__ == "__main__":
    unittest.main()
