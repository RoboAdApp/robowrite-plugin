#!/usr/bin/env python3
"""Behavior locks for scripts/smoke_test.py."""

from __future__ import annotations

import importlib.util
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
        self.assertIsNone(status)
        self.assertEqual(headers, {})
        self.assertIn("dns failed", body)

    def test_timeout_returns_transport_result_instead_of_raising(self) -> None:
        with mock.patch.object(sm, "OPENER", BoomOpener(TimeoutError("timed out"))):
            status, _, body = sm.fetch("https://www.robowrite.ai/api/mcp")
        self.assertIsNone(status)
        self.assertIn("timed out", body)

    def test_rejects_non_http_schemes(self) -> None:
        status, _, body = sm.fetch("file:///etc/passwd")
        self.assertIsNone(status)
        self.assertIn("scheme", body.lower())

    def test_resource_metadata_transport_failure_is_a_labeled_fail(self) -> None:
        with mock.patch.object(sm, "fetch", return_value=(None, {}, "transport error: dns failed")):
            issuer = sm.check_resource_metadata()
        self.assertIsNone(issuer)
        self.assertTrue(
            any("protected-resource metadata" in message and "dns failed" in message for message in sm.failures),
            sm.failures,
        )

    def test_static_client_transport_failure_fails_the_check(self) -> None:
        with mock.patch.object(sm, "fetch", return_value=(None, {}, "transport error: dns failed")):
            sm.check_static_clients("https://clerk.robowrite.ai/oauth/authorize")
        self.assertTrue(sm.failures, sm.failures)
        self.assertTrue(
            any("gemini-extension.json" in message and "dns failed" in message for message in sm.failures),
            sm.failures,
        )

    def test_metadata_document_probe_stays_a_warning_on_transport(self) -> None:
        with mock.patch.object(sm, "fetch", return_value=(None, {}, "transport error: dns failed")):
            sm.check_metadata_document_clients(
                {
                    "client_id_metadata_document_supported": True,
                    "authorization_endpoint": "https://clerk.robowrite.ai/oauth/authorize",
                }
            )
        self.assertEqual(sm.failures, [])
        self.assertTrue(sm.warnings, sm.warnings)


if __name__ == "__main__":
    unittest.main()
