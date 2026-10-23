#!/usr/bin/env python3
"""Behavior locks for scripts/smoke_test.py."""

from __future__ import annotations

import importlib.util
import json
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "smoke_test.py"

spec = importlib.util.spec_from_file_location("smoke_test", SCRIPT)
sm = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(sm)


class BoomOpener:
    def __init__(self, error: BaseException) -> None:
        self.error = error

    def open(self, request, timeout=None):
        raise self.error


class FetchTransport(unittest.TestCase):
    def tearDown(self) -> None:
        sm.failures.clear()
        sm.warnings.clear()

    def test_urlerror_returns_transport_result_instead_of_raising(self) -> None:
        with mock.patch.object(sm, "OPENER", BoomOpener(urllib.error.URLError("dns failed"))):
            status, headers, body = sm.fetch("https://www.robowrite.ai/api/mcp")
        self.assertEqual(status, 0)
        self.assertEqual(headers, {})
        self.assertIn("dns failed", body)

    def test_timeout_returns_transport_result_instead_of_raising(self) -> None:
        with mock.patch.object(sm, "OPENER", BoomOpener(TimeoutError("timed out"))):
            status, _, body = sm.fetch("https://www.robowrite.ai/api/mcp")
        self.assertEqual(status, 0)
        self.assertIn("timed out", body)

    def test_rejects_non_http_schemes(self) -> None:
        status, _, body = sm.fetch("file:///etc/passwd")
        self.assertEqual(status, 0)
        self.assertIn("scheme", body.lower())
        self.assertNotIn("root:", body)

    def test_resource_metadata_transport_failure_is_a_labeled_fail(self) -> None:
        with mock.patch.object(sm, "fetch", return_value=(0, {}, "transport error: dns failed")):
            issuer = sm.check_resource_metadata()
        self.assertIsNone(issuer)
        self.assertTrue(
            any("protected-resource metadata" in message and "dns failed" in message for message in sm.failures),
            sm.failures,
        )

    def test_static_client_transport_failure_fails_the_check(self) -> None:
        with mock.patch.object(sm, "fetch", return_value=(0, {}, "transport error: dns failed")):
            sm.check_static_clients("https://clerk.robowrite.ai/oauth/authorize")
        self.assertTrue(sm.failures, sm.failures)
        self.assertTrue(
            any("gemini-extension.json" in message and "dns failed" in message for message in sm.failures),
            sm.failures,
        )

    def test_metadata_document_probe_stays_a_warning_on_transport(self) -> None:
        with mock.patch.object(sm, "fetch", return_value=(0, {}, "transport error: dns failed")):
            sm.check_metadata_document_clients(
                {
                    "client_id_metadata_document_supported": True,
                    "authorization_endpoint": "https://clerk.robowrite.ai/oauth/authorize",
                }
            )
        self.assertEqual(sm.failures, [])
        self.assertTrue(sm.warnings, sm.warnings)

    def test_unsigned_initialize_401_is_a_failure(self) -> None:
        def fake_fetch(url, *, data=None, headers=None):
            payload = json.loads(data.decode()) if data else {}
            if payload.get("method") == "initialize":
                return 401, {"WWW-Authenticate": f'Bearer resource_metadata="{sm.RESOURCE_METADATA_URL}"'}, "{}"
            if payload.get("method") == "tools/list":
                return 200, {}, "{}"
            if payload.get("method") == "tools/call":
                return 401, {"WWW-Authenticate": f'Bearer resource_metadata="{sm.RESOURCE_METADATA_URL}"'}, "{}"
            return 0, {}, "unexpected"

        with mock.patch.object(sm, "fetch", side_effect=fake_fetch):
            sm.check_unauthenticated_challenge()
        self.assertTrue(
            any("unauthenticated initialize" in message and "401" in message for message in sm.failures),
            sm.failures,
        )

    def test_unsigned_tools_call_must_still_challenge(self) -> None:
        def fake_fetch(url, *, data=None, headers=None):
            payload = json.loads(data.decode()) if data else {}
            if payload.get("method") in {"initialize", "tools/list"}:
                return 200, {}, "{}"
            if payload.get("method") == "tools/call":
                return 200, {}, "{}"
            return 0, {}, "unexpected"

        with mock.patch.object(sm, "fetch", side_effect=fake_fetch):
            sm.check_unauthenticated_challenge()
        self.assertTrue(
            any("unauthenticated tools/call" in message and "200" in message for message in sm.failures),
            sm.failures,
        )

    def test_unsigned_discovery_and_gated_call_pass(self) -> None:
        def fake_fetch(url, *, data=None, headers=None):
            payload = json.loads(data.decode()) if data else {}
            if payload.get("method") in {"initialize", "tools/list"}:
                return 200, {}, "{}"
            if payload.get("method") == "tools/call":
                return (
                    401,
                    {"WWW-Authenticate": f'Bearer resource_metadata="{sm.RESOURCE_METADATA_URL}"'},
                    "{}",
                )
            return 0, {}, "unexpected"

        with mock.patch.object(sm, "fetch", side_effect=fake_fetch):
            sm.check_unauthenticated_challenge()
        self.assertEqual(sm.failures, [])


if __name__ == "__main__":
    unittest.main()
