#!/usr/bin/env python3
"""Smoke-test the hosted service against what the shipped manifests promise.

Read-only and unauthenticated: no sign-in, no tokens, no tool calls. Standard library only.

Usage:
  python3 scripts/smoke_test.py            # failures exit 1, warnings do not
  python3 scripts/smoke_test.py --strict   # warnings also exit 1
"""

from __future__ import annotations

import argparse
import json
import os
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

# A public Client ID Metadata Document that is known to be well formed. Used
# only to check that the authorization server can resolve such documents.
# redirect_uri must be listed in that document; Clerk validates it on the
# hop after /oauth/authorize.
CIMD_PROBE = ("https://vscode.dev/oauth/client-metadata.json", "http://127.0.0.1:33418/")

# Any S256 challenge works; the flow is never completed.
CODE_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"

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
    "get_content": ("content_item_id",),
    "get_job": ("job_id",),
    "list_draft_sections": ("content_item_id", "content_version_id"),
    "get_review_card": ("content_item_id",),
    "list_reviews": (),
    "get_review": ("review_id",),
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
    """Read JSON or the matching JSON-RPC response from an SSE body."""
    content_type = next((value for key, value in headers.items() if key.lower() == "content-type"), "")
    if content_type.split(";", 1)[0].strip().lower() != "text/event-stream":
        return as_json(body)
    data = []
    # SSE line boundaries are CR/LF only; Unicode separators may be JSON text.
    # Discard the final unterminated line; EOF must not dispatch an event.
    for line in body.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n").split("\n")[:-1]:
        if not line:
            if data:
                payload = as_json("\n".join(data))
                if not isinstance(payload, dict):
                    return None
                if type(payload.get("id")) is int and payload["id"] == 1 and ("result" in payload or "error" in payload):
                    return payload
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
    payload: dict = {"jsonrpc": "2.0", "id": 1, "method": method}
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
    required = set(EDITORIAL_READ_IDS) | set(EDITORIAL_BODY_UUIDS)
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
        if not writing:
            keys = EDITORIAL_READ_IDS[name]
            for key in keys:
                field(schema, key, "string", name, uuid=True)
            required_only(schema, set(keys), name)
            if name == "get_content":
                optional_value(schema, "version", "integer", name, nullable=True)
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
        payload = mcp_response(headers, body)
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
        ok("public catalog exposes the saved-draft workflow argument and replay contracts")


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


def authorize_outcome(endpoint: str, client_id: str, redirect_uri: str, scopes: list[str]):
    """Start an authorization request and report how the server treats the client.

    Returns ("accepted" | "rejected" | "error" | "inconclusive", detail), where
    "error" means the server could not be reached. The server
    validates the client on the hop after the first redirect, so follow one hop.
    """
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": CODE_CHALLENGE,
            "code_challenge_method": "S256",
            "state": "smoke",
            "scope": " ".join(scopes),
            "resource": MCP_URL,
        }
    )
    url = f"{endpoint}?{query}"
    for _ in range(3):
        status, headers, body = fetch(url)
        if status == 0:
            return "error", body
        error = as_json(body)
        if isinstance(error, dict) and error.get("error"):
            return "rejected", f"{error['error']}: {error.get('error_description', '')}"
        location = headers.get("Location")
        if status in (301, 302, 303, 307, 308) and location:
            target = urllib.parse.urljoin(url, location)
            if urllib.parse.urlparse(target).netloc != urllib.parse.urlparse(endpoint).netloc:
                # Handed off to the hosted sign-in page: the client and redirect were accepted.
                if "error=" in urllib.parse.urlparse(target).query:
                    return "rejected", f"redirected with an error: {target[:160]}"
                return "accepted", urllib.parse.urlparse(target).netloc
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
    found.append(("mcp.json", cursor["CLIENT_ID"], "http://localhost:8787/callback", cursor["scopes"]))

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
            if "redirect_uri" in detail or detail.startswith("invalid_request"):
                hint = (
                    f" Fix: add {redirect_uri} to the redirect URIs of OAuth application"
                    f" {client_id} in the Clerk dashboard, then re-run this job."
                )
            fail(f"{label} is rejected by the authorization server.{hint} Server said: {detail}")
        else:
            warn(f"{label}: {detail}")


def check_metadata_document_clients(metadata: dict) -> None:
    if not metadata.get("client_id_metadata_document_supported"):
        warn("authorization server does not advertise Client ID Metadata Documents")
        return
    client_id, redirect_uri = CIMD_PROBE
    outcome, detail = authorize_outcome(
        metadata["authorization_endpoint"], client_id, redirect_uri, ["user:org:read", "offline_access"]
    )
    if outcome == "accepted":
        ok("Client ID Metadata Document clients reach sign-in")
    else:
        # The repo cannot fix this, so it does not block a merge unless --strict.
        warn(f"Client ID Metadata Documents are advertised but a known-good document is not accepted ({detail})")


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
