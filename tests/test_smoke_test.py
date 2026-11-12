#!/usr/bin/env python3
"""Behavior locks for scripts/smoke_test.py."""

from __future__ import annotations

import copy
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
CATALOG = ROOT / "tests" / "fixtures" / "editorial-catalog.json"


def catalog_payload() -> dict:
    return json.loads(CATALOG.read_text())


def rpc_result(result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": sm.MCP_REQUEST_ID, "result": result}


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
            status, headers, body = sm.fetch("https://mcp.robowrite.ai/mcp")
        self.assertEqual(status, 0)
        self.assertEqual(headers, {})
        self.assertIn("dns failed", body)

    def test_timeout_returns_transport_result_instead_of_raising(self) -> None:
        with mock.patch.object(sm, "OPENER", BoomOpener(TimeoutError("timed out"))):
            status, _, body = sm.fetch("https://mcp.robowrite.ai/mcp")
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
                return 200, {}, CATALOG.read_text()
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
            if payload.get("method") == "tools/list":
                return 200, {}, CATALOG.read_text()
            if payload.get("method") == "initialize":
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
            if payload.get("method") == "tools/list":
                return 200, {}, CATALOG.read_text()
            if payload.get("method") == "initialize":
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


class EditorialCatalogContract(unittest.TestCase):
    def setUp(self) -> None:
        self.tools = catalog_payload()["result"]["tools"]

    def tearDown(self) -> None:
        sm.failures.clear()

    def tool(self, name: str) -> dict:
        return next(tool for tool in self.tools if tool["name"] == name)

    def test_current_public_schema_and_additive_optional_fields_are_allowed(self) -> None:
        self.tools.append({"name": "unrelated_future_tool"})
        self.tool("edit_draft")["inputSchema"]["properties"]["body"]["properties"]["future_option"] = {"type": "boolean"}
        self.assertEqual(sm.editorial_catalog_errors(self.tools), [])

    def test_equivalent_nullable_type_arrays_are_allowed(self) -> None:
        for nested in (False, True):
            with self.subTest(nested=nested):
                tools = copy.deepcopy(self.tools)
                edit = next(tool for tool in tools if tool["name"] == "edit_draft")
                content = next(tool for tool in tools if tool["name"] == "get_content")
                string = {"type": ["string", "null"]}
                integer = {"type": ["integer", "null"], "minimum": 1}
                edit["inputSchema"]["properties"]["body"]["properties"]["markdown_body"] = {"anyOf": [string]} if nested else string
                content["inputSchema"]["properties"]["version"] = {"anyOf": [integer]} if nested else integer
                self.assertEqual(sm.editorial_catalog_errors(tools), [])

    def test_anyof_branches_intersect_root_types_instead_of_overriding_them(self) -> None:
        for root in ("string", ["string", "null"]):
            with self.subTest(root=root):
                tools = copy.deepcopy(self.tools)
                schema = next(tool for tool in tools if tool["name"] == "get_content")["inputSchema"]
                schema["properties"]["version"] = {"type": root, "anyOf": [{"type": "integer"}, {"type": "null"}]}
                self.assertTrue(any("get_content.version" in error for error in sm.editorial_catalog_errors(tools)))
        for root in (["integer", "null"], ["number", "null"]):
            with self.subTest(compatible_root=root):
                schema = self.tool("get_content")["inputSchema"]
                schema["properties"]["version"] = {"type": root, "anyOf": [{"anyOf": [{"type": "integer"}, {"type": "null"}]}]}
                self.assertEqual(sm.editorial_catalog_errors(self.tools), [])
        for schema in ({}, {"anyOf": [{}]}, {"type": ["integer", "null"], "anyOf": [{}]}):
            with self.subTest(unconstrained_branch=schema):
                self.tool("get_content")["inputSchema"]["properties"]["version"] = schema
                self.assertEqual(sm.editorial_catalog_errors(self.tools), [])

    def test_missing_tool_names_the_unavailable_operation(self) -> None:
        tools = [tool for tool in self.tools if tool["name"] != "edit_draft"]
        self.assertIn("missing required tool edit_draft", sm.editorial_catalog_errors(tools))

    def test_version_binding_cannot_disappear_or_become_optional(self) -> None:
        for removal in ("properties", "required"):
            with self.subTest(removal=removal):
                tools = copy.deepcopy(self.tools)
                candidate = next(tool for tool in tools if tool["name"] == "edit_draft")["inputSchema"]["properties"]["body"]
                if removal == "properties":
                    candidate[removal].pop("expected_base_version_id")
                else:
                    candidate[removal].remove("expected_base_version_id")
                self.assertTrue(any("expected_base_version_id" in error for error in sm.editorial_catalog_errors(tools)))

    def test_new_required_argument_is_a_contract_break(self) -> None:
        body = self.tool("restore_draft")["inputSchema"]["properties"]["body"]
        body["properties"]["new_requirement"] = {"type": "string"}
        body["required"].append("new_requirement")
        self.assertTrue(any("new_requirement" in error for error in sm.editorial_catalog_errors(self.tools)))

    def test_exact_version_selector_retains_optional_nullable_integer_contract(self) -> None:
        for replacement in (
            None, {"type": "string"}, {"type": "integer"},
            {"anyOf": [{"type": "string"}, {"type": "null"}]},
            {"anyOf": [{"type": "null"}]}, {"anyOf": [{"type": {}}]},
            {"anyOf": [{"type": "integer"}, {"type": "null"}, None]},
            {"type": ["integer", "null", {}]}, {"type": ["integer", "null", "unknown"]},
        ):
            with self.subTest(replacement=replacement):
                tools = copy.deepcopy(self.tools)
                schema = next(tool for tool in tools if tool["name"] == "get_content")["inputSchema"]
                if replacement is None:
                    schema["properties"].pop("version")
                else:
                    schema["properties"]["version"] = replacement
                self.assertTrue(any("get_content.version" in error for error in sm.editorial_catalog_errors(tools)))
        self.tool("get_content")["inputSchema"]["required"].append("version")
        self.assertTrue(any("version" in error for error in sm.editorial_catalog_errors(self.tools)))

    def test_documented_edit_and_section_rewrite_payloads_cannot_disappear_or_change_type(self) -> None:
        for name, keys in (("edit_draft", ("markdown_body", "target", "replacement")), ("rewrite_draft", ("section_id",))):
            for key in keys:
                for replacement in (None, {"type": "integer"}, {"anyOf": [{"type": "null"}]}):
                    with self.subTest(name=name, key=key, replacement=replacement):
                        tools = copy.deepcopy(self.tools)
                        properties = next(tool for tool in tools if tool["name"] == name)["inputSchema"]["properties"]["body"]["properties"]
                        if replacement is None:
                            properties.pop(key)
                        else:
                            properties[key] = replacement
                        self.assertTrue(any(f"{name}.body.{key}" in error for error in sm.editorial_catalog_errors(tools)))

    def test_replay_identifier_type_and_uuid_format_are_preserved(self) -> None:
        request_id = self.tool("decide_review")["inputSchema"]["properties"]["body"]["properties"]["request_id"]
        for value in ({"type": "integer"}, {"type": "string"}):
            with self.subTest(value=value):
                request_id.clear()
                request_id.update(value)
                self.assertTrue(any("request_id" in error for error in sm.editorial_catalog_errors(self.tools)))

    def test_decision_choices_cannot_lose_revision_requests(self) -> None:
        action = self.tool("decide_review")["inputSchema"]["properties"]["body"]["properties"]["action"]
        action["enum"].remove("request_revision")
        self.assertTrue(any("decision choices" in error for error in sm.editorial_catalog_errors(self.tools)))

    def test_rewrite_key_required_and_other_write_keys_forbidden(self) -> None:
        self.tool("rewrite_draft")["inputSchema"]["required"].remove("idempotency_key")
        self.assertTrue(any("idempotency_key" in error for error in sm.editorial_catalog_errors(self.tools)))
        self.tools = catalog_payload()["result"]["tools"]
        self.tool("edit_draft")["inputSchema"]["properties"]["idempotency_key"] = {"type": "string"}
        self.assertTrue(any("edit_draft must reject" in error for error in sm.editorial_catalog_errors(self.tools)))

    def test_broader_repair_cannot_default_on_or_claim_read_only(self) -> None:
        self.tool("rewrite_draft")["inputSchema"]["properties"]["body"]["properties"]["allow_broader_repair"]["default"] = True
        self.tool("rewrite_draft")["annotations"]["readOnlyHint"] = True
        errors = sm.editorial_catalog_errors(self.tools)
        self.assertTrue(any("broader repair" in error for error in errors))
        self.assertTrue(any("readOnlyHint" in error for error in errors))

    def test_malformed_choice_schema_returns_findings_not_an_exception(self) -> None:
        self.tool("decide_review")["inputSchema"]["properties"]["body"]["properties"]["action"]["enum"] = [{}]
        self.assertTrue(sm.editorial_catalog_errors(self.tools))

    def test_pagination_finds_required_tools_without_a_fixed_catalog_size(self) -> None:
        first, second = self.tools[:2], self.tools[2:]
        pages = [
            (200, {}, json.dumps(rpc_result({"tools": first, "nextCursor": "next"}))),
            (200, {}, json.dumps(rpc_result({"tools": second}))),
        ]
        with mock.patch.object(sm, "mcp_post", side_effect=pages):
            sm.check_public_tool_catalog()
        self.assertEqual(sm.failures, [])

    def test_malformed_catalog_and_repeated_cursor_are_failures(self) -> None:
        with mock.patch.object(sm, "mcp_post", return_value=(200, {}, "{}")):
            sm.check_public_tool_catalog()
        self.assertTrue(any("expected a tool catalog" in failure for failure in sm.failures))
        sm.failures.clear()
        repeated = (200, {}, json.dumps(rpc_result({"tools": [], "nextCursor": "again"})))
        with mock.patch.object(sm, "mcp_post", side_effect=[repeated, repeated]) as post:
            sm.check_public_tool_catalog()
        self.assertIn("unauthenticated tools/list returned an invalid or repeated pagination cursor", sm.failures)
        self.assertEqual(post.call_count, 2)

    def test_unbounded_unique_cursors_fail_at_the_catalog_limit(self) -> None:
        pages = iter((200, {}, json.dumps(rpc_result({"tools": [], "nextCursor": str(page)}))) for page in range(3))
        with mock.patch.object(sm, "MAX_CATALOG_PAGES", 2), mock.patch.object(sm, "mcp_post", side_effect=lambda *args: next(pages)):
            sm.check_public_tool_catalog()
        self.assertTrue(any("2-page catalog limit" in message for message in sm.failures))
        self.assertEqual(json.loads(next(pages)[2])["result"]["nextCursor"], "2")

    def test_catalog_correlates_json_and_sse_responses_to_the_numeric_request(self) -> None:
        valid = rpc_result({"tools": self.tools})
        variants = []
        for request_id in (None, True, "1", 2):
            payload = copy.deepcopy(valid)
            if request_id is None:
                payload.pop("id")
            else:
                payload["id"] = request_id
            variants.append((payload, False))
        variants.append(({**valid, "jsonrpc": "1.0"}, False))
        variants.append(({**valid, "error": {"code": -32600, "message": "Invalid Request"}}, False))
        variants.extend([(valid, True), ({**valid, "id": 1.0}, True)])
        for payload, accepted in variants:
            for sse in (False, True):
                body = json.dumps(payload)
                headers = {"Content-Type": "text/event-stream" if sse else "application/json"}
                if sse:
                    body = "data: " + body + "\n\n"
                with self.subTest(id=payload.get("id"), version=payload.get("jsonrpc"), error="error" in payload, sse=sse), mock.patch.object(sm, "mcp_post", return_value=(200, headers, body)):
                    sm.check_public_tool_catalog()
                    self.assertEqual(not sm.failures, accepted)
                    sm.failures.clear()

    def test_sse_catalog_skips_notifications_and_matches_response_across_pages(self) -> None:
        self.tools[0]["description"] = "Read account\u2028without modifying it"
        pages = []
        for tools, cursor in ((self.tools[:2], "next"), (self.tools[2:], None)):
            result = {"tools": tools}
            if cursor:
                result["nextCursor"] = cursor
            response = json.dumps({"jsonrpc": "2.0", "id": 1, "result": result}, indent=2, ensure_ascii=False)
            events = ': keepalive\r\n\r\ndata: {"jsonrpc":"2.0","method":"notifications/progress"}\r\n\r\n'
            events += 'data: {"jsonrpc":"2.0","id":2,"result":{"tools":[]}}\r\n\r\n'
            events += "\r\n".join("data: " + line for line in response.split("\n")) + "\r\n\r\n"
            pages.append((200, {"content-type": "text/event-stream; charset=utf-8"}, events))
        with mock.patch.object(sm, "mcp_post", side_effect=pages):
            sm.check_public_tool_catalog()
        self.assertEqual(sm.failures, [])

    def test_sse_malformed_or_unmatched_response_is_a_catalog_failure(self) -> None:
        for body in ('data: invalid\n\n', 'data: {"id":2,"result":{"tools":[]}}\n\n', ': keepalive\n\n'):
            with self.subTest(body=body), mock.patch.object(sm, "mcp_post", return_value=(200, {"Content-Type": "text/event-stream"}, body)):
                sm.check_public_tool_catalog()
                self.assertTrue(any("expected a tool catalog" in message for message in sm.failures))
                sm.failures.clear()

    def test_sse_requires_a_real_blank_line_delimiter_before_dispatch(self) -> None:
        event = "data: " + json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"tools": self.tools}})
        for ending in ("", "\n", "\r\n", "\r"):
            with self.subTest(ending=ending), mock.patch.object(sm, "mcp_post", return_value=(200, {"Content-Type": "text/event-stream"}, event + ending)):
                sm.check_public_tool_catalog()
                self.assertTrue(any("expected a tool catalog" in message for message in sm.failures))
                sm.failures.clear()
        for ending in ("\n\n", "\r\n\r\n", "\r\r"):
            with self.subTest(ending=ending), mock.patch.object(sm, "mcp_post", return_value=(200, {"Content-Type": "text/event-stream"}, "\ufeff" + event + ending)):
                sm.check_public_tool_catalog()
                self.assertEqual(sm.failures, [])


if __name__ == "__main__":
    unittest.main()
