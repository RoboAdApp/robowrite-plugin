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

MCP_URL = "https://www.robowrite.ai/api/mcp"
RESOURCE_METADATA_URL = "https://www.robowrite.ai/.well-known/oauth-protected-resource/api/mcp"
TIMEOUT = 20
USER_AGENT = "robowrite-plugin-smoke/1"

# A public Client ID Metadata Document that is known to be well formed. Used
# only to check that the authorization server can resolve such documents.
CIMD_PROBE = ("https://claude.ai/oauth/claude-code-client-metadata", "http://localhost:8787/callback")

# Any S256 challenge works; the flow is never completed.
CODE_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"

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


def check_unauthenticated_challenge() -> None:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "robowrite-plugin-smoke", "version": "1"},
        },
    }
    status, headers, body = fetch(
        MCP_URL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
    )
    challenge = headers.get("WWW-Authenticate", "")
    if status != 401:
        fail(f"unauthenticated initialize: {describe(status, body)}, expected HTTP 401")
    elif RESOURCE_METADATA_URL not in challenge:
        fail(f"unauthenticated initialize: WWW-Authenticate does not point at the resource metadata ({challenge!r})")
    else:
        ok("unauthenticated initialize returns 401 with an OAuth challenge")


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
