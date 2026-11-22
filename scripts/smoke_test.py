#!/usr/bin/env python3
"""Smoke-test the hosted service against what the shipped manifests promise.

Read-only and unauthenticated: no sign-in, no tokens, no tool calls. Standard library only.

Usage:
  python3 scripts/smoke_test.py            # failures exit 1, warnings do not
  python3 scripts/smoke_test.py --strict   # warnings also exit 1
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MCP_URL = "https://mcp.robowrite.ai/mcp"
_resource = urllib.parse.urlsplit(MCP_URL)
RESOURCE_METADATA_URL = urllib.parse.urlunsplit(
    (_resource.scheme, _resource.netloc, f"/.well-known/oauth-protected-resource{_resource.path}", "", "")
)
TIMEOUT = 20
MAX_CATALOG_PAGES = 100
USER_AGENT = "robowrite-plugin-smoke/1"
JSONRPC_VERSION = "2.0"
MCP_REQUEST_ID = 1

# Signed-out probes stop at this handoff without opening it.
SIGN_IN_URL = "https://accounts.robowrite.ai/sign-in"
CODEX_CLIENT = "https://chatgpt.com/oauth/codex/client.json"
CHATGPT_CLIENT = "https://chatgpt.com/oauth/client.json"
OPENAI_RECONNECT_SCOPES = (
    "user:org:read", "robowrite:content", "robowrite:organizations:read",
    "robowrite:content:all_orgs", "offline_access",
)

# These are contracts promised by the saved-draft workflow, not a fixed size for
# the entire catalog. This smoke targets the canonical public server; a native
# client's filtered inventory is checked per requested operation by the skill.
EDITORIAL_BODY_UUIDS = {
    "edit_draft": ("expected_base_version_id", "request_id"),
    "restore_draft": ("expected_base_version_id", "request_id", "source_version_id"),
    "rewrite_draft": ("expected_base_version_id",),
    "check_draft": ("expected_base_version_id", "request_id"),
    "request_review": ("content_version_id",),
    "decide_review": ("content_version_id", "request_id"),
}
EDITORIAL_READ_IDS = {
    "get_account": (),
    "list_brands": (),
    "list_content": (),
    "list_briefs": (),
    "list_jobs": (),
    "read_draft": ("content_item_id",),
    "get_content": ("content_item_id",),
    "get_job": ("job_id",),
    "list_draft_sections": ("content_item_id", "content_version_id"),
    "get_review_card": ("content_item_id",),
    "list_reviews": (),
    "get_review": ("review_id",),
}
# Search arguments used to recover existing work before any write or retry.
CONTENT_SEARCH_FIELDS = (
    "brand_id", "property_id", "status", "format", "pillar_id", "keyword",
    "created_from", "created_before", "q",
)
RECOVERY_SEARCH_FIELDS = {
    "list_content": (*CONTENT_SEARCH_FIELDS, "brief_id", "content_type"),
    "list_briefs": CONTENT_SEARCH_FIELDS,
    "list_jobs": ("brand_id", "content_item_id", "created_from", "created_before"),
}
# New packaged connections require these live read-only operations before use.
WORKSPACE_READ_IDS = {
    "list_organizations": (),
    "get_organization_access": ("organization_id",),
    "switch_organization": ("organization_id",),
}
SCHEMA_TYPES = frozenset(("null", "boolean", "object", "array", "number", "integer", "string"))

failures: list[str] = []
warnings: list[str] = []


def ok(message: str) -> None:
    print(f"PASS {message}")


def fail(message: str) -> None:
    failures.append(message)
    print(f"::error::{message}" if os.environ.get("GITHUB_ACTIONS") else f"FAIL {message}")


def warn(message: str) -> None:
    warnings.append(message)
    print(f"::warning::{message}" if os.environ.get("GITHUB_ACTIONS") else f"WARN {message}")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def fetch(url: str, *, data: bytes | None = None, headers: dict | None = None):
    """Return (status, headers, body) without following redirects or raising on 4xx.

    DNS, TLS, connection and timeout failures come back as status 0 with the
    error as the body, so each check can report them under its own label.
    """
    scheme = urllib.parse.urlparse(url).scheme
    if scheme not in ("http", "https"):
        return 0, {}, f"unsupported URL scheme {scheme!r}"
    request = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with OPENER.open(request, timeout=TIMEOUT) as response:
            return response.status, response.headers, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        reason = getattr(error, "reason", error)
        return 0, {}, f"transport error reaching {url}: {reason}"


def describe(status: int, body: str) -> str:
    return body if status == 0 else f"HTTP {status}"


def as_json(body: str):
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return None


def mcp_response(headers: dict, body: str):
    """Read the matching JSON-RPC response from JSON or SSE."""
    def matching_response(payload):
        if (
            isinstance(payload, dict) and payload.get("jsonrpc") == JSONRPC_VERSION
            and type(payload.get("id")) in (int, float) and payload["id"] == MCP_REQUEST_ID
            and (("result" in payload) != ("error" in payload))
        ):
            return payload
        return None

    content_type = next((value for key, value in headers.items() if key.lower() == "content-type"), "")
    if content_type.split(";", 1)[0].strip().lower() != "text/event-stream":
        return matching_response(as_json(body))
    data = []
    # SSE line boundaries are CR/LF only; Unicode separators may be JSON text.
    # Discard the final unterminated line; EOF must not dispatch an event.
    for line in body.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n").split("\n")[:-1]:
        if not line:
            if data:
                event_data = "\n".join(data)
                if not event_data:
                    # MCP permits an empty-data SSE event to prime reconnection.
                    data = []
                    continue
                try:
                    payload = json.loads(event_data)
                except json.JSONDecodeError as exc:
                    raise ValueError("SSE data contains malformed JSON") from exc
                if not isinstance(payload, dict):
                    raise ValueError("SSE data must be a JSON object")
                response = matching_response(payload)
                if response is not None:
                    return response
            data = []
        elif line.startswith("data:"):
            value = line[5:]
            data.append(value[1:] if value.startswith(" ") else value)
    return None


def check_resource_metadata() -> str | None:
    status, _, body = fetch(RESOURCE_METADATA_URL)
    metadata = as_json(body)
    if status != 200 or not isinstance(metadata, dict):
        fail(f"protected-resource metadata: {describe(status, body)}, expected HTTP 200 JSON")
        return None
    if metadata.get("resource") != MCP_URL:
        fail(f"protected-resource metadata: resource is {metadata.get('resource')}, expected {MCP_URL}")
    servers = metadata.get("authorization_servers") or []
    if not servers:
        fail("protected-resource metadata: no authorization_servers")
        return None
    ok(f"protected-resource metadata names {servers[0]}")
    return servers[0].rstrip("/")


def mcp_post(method: str, params: dict | None = None):
    payload: dict = {"jsonrpc": JSONRPC_VERSION, "id": MCP_REQUEST_ID, "method": method}
    if params is not None:
        payload["params"] = params
    return fetch(
        MCP_URL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
    )


def editorial_catalog_errors(tools: list) -> list[str]:
    """Check exposed argument/replay contracts without invoking any tool."""
    errors = []
    catalog = {}
    for tool in tools:
        name = tool.get("name") if isinstance(tool, dict) else None
        if not isinstance(name, str) or not name or name in catalog:
            errors.append("catalog entries must have unique nonempty names")
            continue
        catalog[name] = tool
    read_ids = EDITORIAL_READ_IDS | WORKSPACE_READ_IDS
    required = set(read_ids) | set(EDITORIAL_BODY_UUIDS)
    for name in sorted(required - catalog.keys()):
        errors.append(f"missing required tool {name}")

    def field(schema: dict, key: str, kind: str, location: str, *, uuid: bool = False) -> dict:
        properties = schema.get("properties", {})
        value = properties.get(key, {}) if isinstance(properties, dict) else {}
        required_fields = schema.get("required", [])
        if (
            not isinstance(value, dict) or value.get("type") != kind
            or not isinstance(required_fields, list) or key not in required_fields
            or (uuid and value.get("format") != "uuid")
        ):
            errors.append(f"{location}.{key} must remain a required {kind}" + (" UUID" if uuid else ""))
        return value if isinstance(value, dict) else {}

    def required_only(schema: dict, allowed: set[str], location: str) -> None:
        keys = schema.get("required", [])
        if not isinstance(keys, list) or any(not isinstance(key, str) for key in keys):
            errors.append(f"{location} required fields must be names")
        elif extra := set(keys) - allowed:
            errors.append(f"{location} adds undocumented required fields: {', '.join(sorted(extra))}")

    def asserted_types(schema) -> set[str]:
        """Coarsely project supported type/anyOf constraints, not all JSON Schema."""
        if isinstance(schema, bool):
            return set(SCHEMA_TYPES) if schema else set()
        if not isinstance(schema, dict):
            raise ValueError("type schemas must be objects or booleans")
        types = set(SCHEMA_TYPES)
        if "type" in schema:
            declared = schema["type"]
            choices = [declared] if isinstance(declared, str) else declared if isinstance(declared, list) else []
            if not choices or any(not isinstance(choice, str) or choice not in SCHEMA_TYPES for choice in choices) or len(set(choices)) != len(choices):
                raise ValueError("type must name unique supported JSON types")
            types = set(choices)
            if "number" in types:
                types.add("integer")
        if "anyOf" in schema:
            branches = schema["anyOf"]
            if not isinstance(branches, list) or not branches:
                raise ValueError("anyOf must contain schemas")
            types &= set().union(*(asserted_types(branch) for branch in branches))
        return types

    def optional_value(schema: dict, key: str, kind: str, location: str, *, nullable: bool = False) -> None:
        properties = schema.get("properties", {})
        value = properties.get(key) if isinstance(properties, dict) else None
        try:
            types = asserted_types(value)
        except ValueError:
            errors.append(f"{location}.{key} must expose a valid supported type schema")
            return
        if kind not in types or (nullable and "null" not in types):
            errors.append(f"{location}.{key} must retain a " + ("nullable " if nullable else "") + f"{kind} payload schema")

    for name in sorted(required & catalog.keys()):
        tool = catalog[name]
        schema = tool.get("inputSchema")
        writing = name in EDITORIAL_BODY_UUIDS
        if not isinstance(schema, dict) or schema.get("type") != "object":
            errors.append(f"{name} must expose an object input schema")
            continue
        annotations = tool.get("annotations", {})
        if not isinstance(annotations, dict) or annotations.get("readOnlyHint") is not (not writing):
            errors.append(f"{name} readOnlyHint does not match its documented operation")
        if name not in WORKSPACE_READ_IDS:
            optional_value(schema, "organization_id", "string", name)
        if not writing:
            keys = read_ids[name]
            for key in keys:
                field(schema, key, "string", name, uuid=name not in WORKSPACE_READ_IDS)
            required_only(schema, set(keys), name)
            if name == "get_content":
                optional_value(schema, "version", "integer", name, nullable=True)
            if name in ("list_reviews", "list_organizations", "list_brands") or name in RECOVERY_SEARCH_FIELDS:
                for key in ("offset", "limit"):
                    optional_value(schema, key, "integer", name)
            for key in RECOVERY_SEARCH_FIELDS.get(name, ()):
                optional_value(schema, key, "string", name)
            continue
        root_fields = {"body"}
        if name != "request_review":
            item_key = "review_id" if name == "decide_review" else "content_item_id"
            field(schema, item_key, "string", name, uuid=True)
            root_fields.add(item_key)
        if name == "rewrite_draft":
            root_fields.add("idempotency_key")
        required_only(schema, root_fields, name)
        body = field(schema, "body", "object", name)
        for key in EDITORIAL_BODY_UUIDS[name]:
            field(body, key, "string", f"{name}.body", uuid=True)
        body_fields = set(EDITORIAL_BODY_UUIDS[name])
        if name == "decide_review":
            body_fields.add("action")
        required_only(body, body_fields, f"{name}.body")
        properties = schema.get("properties", {})
        if name == "edit_draft":
            for key in ("markdown_body", "target", "replacement"):
                optional_value(body, key, "string", f"{name}.body")
        if name == "rewrite_draft":
            optional_value(body, "section_id", "string", f"{name}.body")
            key = field(schema, "idempotency_key", "string", name)
            if type(key.get("minLength")) is not int or key["minLength"] < 1:
                errors.append("rewrite_draft idempotency_key must exclude empty keys")
            body_fields = body.get("properties", {})
            body_fields = body_fields if isinstance(body_fields, dict) else {}
            scope = body_fields.get("scope", {})
            scope = scope if isinstance(scope, dict) else {}
            choices = scope.get("enum")
            if scope.get("type") != "string" or not isinstance(choices, list) or any(not isinstance(value, str) for value in choices) or not {"section", "full"}.issubset(choices):
                errors.append("rewrite_draft must retain section/full scope choices")
            repair = body_fields.get("allow_broader_repair", {})
            repair = repair if isinstance(repair, dict) else {}
            if repair.get("type") != "boolean" or repair.get("default") is not False:
                errors.append("rewrite_draft broader repair must remain opt-in")
        elif not isinstance(properties, dict) or "idempotency_key" in properties or schema.get("additionalProperties") is not False:
            errors.append(f"{name} must reject an idempotency_key argument; replay uses the documented body fields")
        if name == "decide_review":
            optional_value(body, "feedback", "string", f"{name}.body")
            action = field(body, "action", "string", f"{name}.body")
            choices = action.get("enum")
            if not isinstance(choices, list) or any(not isinstance(value, str) for value in choices) or not {"approve", "reject", "request_revision"}.issubset(choices):
                errors.append("decide_review must retain explicit human decision choices")
    return errors


def check_public_tool_catalog() -> None:
    tools = []
    cursor = None
    seen = set()
    for _ in range(MAX_CATALOG_PAGES):
        status, headers, body = mcp_post("tools/list", {"cursor": cursor} if cursor else None)
        try:
            payload = mcp_response(headers, body)
        except ValueError as exc:
            fail(f"unauthenticated tools/list: {exc}")
            return
        result = payload.get("result") if isinstance(payload, dict) else None
        if status != 200 or not isinstance(result, dict) or not isinstance(result.get("tools"), list):
            fail(f"unauthenticated tools/list: {describe(status, body)}, expected a tool catalog")
            return
        tools.extend(result["tools"])
        cursor = result.get("nextCursor")
        if cursor is None:
            break
        if not isinstance(cursor, str) or not cursor or cursor in seen:
            fail("unauthenticated tools/list returned an invalid or repeated pagination cursor")
            return
        seen.add(cursor)
    else:
        fail(f"unauthenticated tools/list exceeded the {MAX_CATALOG_PAGES}-page catalog limit")
        return
    errors = editorial_catalog_errors(tools)
    for message in errors:
        fail(f"public catalog: {message}")
    if not errors:
        ok("public catalog exposes workspace selection and saved-draft workflow argument/replay contracts")


def check_unauthenticated_challenge() -> None:
    """ChatGPT lists tools before attaching a Bearer; tools/call stays gated."""
    status, _, body = mcp_post(
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "robowrite-plugin-smoke", "version": "1"},
        },
    )
    if status != 200:
        fail(f"unauthenticated initialize: {describe(status, body)}, expected HTTP 200")
    else:
        ok("unauthenticated initialize succeeds so hosts can discover the server")

    check_public_tool_catalog()

    status, headers, body = mcp_post("tools/call", {"name": "get_account", "arguments": {}})
    challenge = headers.get("WWW-Authenticate", "")
    if status != 401:
        fail(f"unauthenticated tools/call: {describe(status, body)}, expected HTTP 401")
    elif RESOURCE_METADATA_URL not in challenge:
        fail(f"unauthenticated tools/call: WWW-Authenticate does not point at the resource metadata ({challenge!r})")
    else:
        ok("unauthenticated tools/call returns 401 with an OAuth challenge")


def check_authorization_server(issuer: str) -> dict | None:
    status, _, body = fetch(f"{issuer}/.well-known/oauth-authorization-server")
    metadata = as_json(body)
    if status != 200 or not isinstance(metadata, dict):
        fail(f"authorization-server metadata: {describe(status, body)}, expected HTTP 200 JSON")
        return None
    if "S256" not in (metadata.get("code_challenge_methods_supported") or []):
        fail("authorization server does not advertise PKCE S256")
    if "none" not in (metadata.get("token_endpoint_auth_methods_supported") or []):
        fail("authorization server does not allow public clients (auth method `none`)")
    if not str(metadata.get("authorization_endpoint", "")).startswith("https://"):
        fail("authorization server has no https authorization_endpoint")
        return None
    ok("authorization server advertises PKCE S256 and public clients")
    return metadata


def oauth_error_label(value: object) -> str:
    # Report only protocol categories. Provider details can echo request data.
    if value in ("invalid_client", "invalid_request", "invalid_scope", "unauthorized_client",
                 "access_denied", "unsupported_response_type", "server_error", "temporarily_unavailable"):
        return str(value)
    return "OAuth error"


def authorize_outcome(endpoint: str, client_id: str, redirect_uri: str, scopes: list[str]):
    """Start an authorization request and report how the server treats the client.

    Returns ("accepted" | "rejected" | "error" | "inconclusive", detail), where
    "error" means the server could not be reached. The server
    validates the client on the hop after the first redirect, so follow one hop.
    """
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": base64.urlsafe_b64encode(digest).decode("ascii").rstrip("="),
            "code_challenge_method": "S256",
            "state": secrets.token_urlsafe(24),
            "scope": " ".join(scopes),
            "resource": MCP_URL,
        }
    )
    url = f"{endpoint}?{query}"
    issuer = urllib.parse.urlsplit(endpoint)
    for _ in range(3):
        status, headers, body = fetch(url)
        if status == 0:
            # A transport exception can include the full authorization URL.
            return "error", "authorization request could not reach the issuer"
        error = as_json(body)
        if isinstance(error, dict) and error.get("error"):
            return "rejected", oauth_error_label(error["error"])
        location = headers.get("Location")
        if status in (301, 302, 303, 307, 308) and location:
            target = urllib.parse.urljoin(url, location)
            destination = urllib.parse.urlsplit(target)
            params = urllib.parse.parse_qs(destination.query, keep_blank_values=True)
            fragment = urllib.parse.parse_qs(destination.fragment, keep_blank_values=True)
            for values in (params, fragment):
                if "error" in values:
                    return "rejected", oauth_error_label(values["error"][0])
            if destination._replace(query="", fragment="").geturl() == SIGN_IN_URL:
                return "accepted", SIGN_IN_URL
            if (destination.scheme, destination.netloc, destination.path) != (
                issuer.scheme, issuer.netloc, "/oauth/authorize/continue",
            ):
                return "inconclusive", "unexpected authorization redirect"
            url = target
            continue
        return "inconclusive", f"HTTP {status} without an OAuth result"
    return "inconclusive", "too many redirects inside the authorization server"


def static_clients() -> list[tuple[str, str, str, list[str]]]:
    """(manifest, client_id, redirect_uri, scopes) for every manifest that ships a static client."""
    found = []

    claude = json.loads((ROOT / ".mcp.json").read_text())["mcpServers"]["robowrite"]["oauth"]
    found.append(
        (
            ".mcp.json",
            claude["clientId"],
            f"http://localhost:{claude['callbackPort']}/callback",
            claude["scopes"].split(),
        )
    )

    cursor = json.loads((ROOT / "mcp.json").read_text())["mcpServers"]["robowrite"]["auth"]
    # Cursor uses separate fixed return addresses for desktop and web/Agents.
    for redirect_uri in ("http://localhost:8787/callback", "https://www.cursor.com/agents/mcp/oauth/callback"):
        found.append(("mcp.json", cursor["CLIENT_ID"], redirect_uri, cursor["scopes"]))

    grok = json.loads((ROOT / "mcp.grok.json").read_text())["mcpServers"]["robowrite"]
    # A registration pinned to one port would break the next native sign-in.
    for port in (51111, 65004):
        found.append(("mcp.grok.json", grok["oauth_client_id"], f"http://127.0.0.1:{port}/callback", grok["oauth_scopes"]))

    gemini = json.loads((ROOT / "gemini-extension.json").read_text())["mcpServers"]["robowrite"]["oauth"]
    found.append(("gemini-extension.json", gemini["clientId"], gemini["redirectUri"], gemini["scopes"]))

    return found


def check_static_clients(endpoint: str) -> None:
    for manifest, client_id, redirect_uri, scopes in static_clients():
        outcome, detail = authorize_outcome(endpoint, client_id, redirect_uri, scopes)
        label = f"{manifest}: client {client_id} with redirect {redirect_uri}"
        if outcome == "accepted":
            ok(f"{label} reaches sign-in")
        elif outcome == "error":
            fail(f"{label}: {detail}")
        elif outcome == "rejected":
            hint = ""
            if detail == "invalid_request":
                hint = (
                    f" Check whether {redirect_uri} is an allowed redirect URI for OAuth application"
                    f" {client_id} in the Clerk dashboard, then re-run this job."
                )
            fail(f"{label} is rejected by the authorization server.{hint} Server said: {detail}")
        else:
            warn(f"{label}: {detail}")


def check_metadata_document_clients(metadata: dict) -> None:
    if not metadata.get("client_id_metadata_document_supported"):
        warn("authorization server does not advertise Client ID Metadata Documents")
        return
    # Exercise the port-bearing redirect sent by a native client. No listener is
    # required because this probe never signs in or follows a callback.
    native_port = 49152 + secrets.randbelow(16384)
    for label, client, callback, scopes in (
        ("Codex desktop", CODEX_CLIENT, f"http://127.0.0.1:{native_port}/callback", OPENAI_RECONNECT_SCOPES),
        ("ChatGPT web", CHATGPT_CLIENT, "https://chatgpt.com/connector_platform_oauth_redirect", OPENAI_RECONNECT_SCOPES),
        ("VS Code", "https://vscode.dev/oauth/client-metadata.json", "http://127.0.0.1:33418/", ("user:org:read", "offline_access")),
    ):
        outcome, detail = authorize_outcome(metadata["authorization_endpoint"], client, callback, list(scopes))
        if outcome == "accepted":
            ok(f"{label} reaches RoboWrite sign-in")
        else:
            warn(f"{label} did not reach RoboWrite sign-in ({detail})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    args = parser.parse_args()

    issuer = check_resource_metadata()
    check_unauthenticated_challenge()
    metadata = check_authorization_server(issuer) if issuer else None
    if metadata:
        check_static_clients(metadata["authorization_endpoint"])
        check_metadata_document_clients(metadata)

    print(f"\n{len(failures)} failed, {len(warnings)} warnings")
    if failures or (args.strict and warnings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
