# RoboWrite

Plan SEO and GEO content using keyword research, competitor research, your brand voice and relevant material from your RoboWrite knowledge library. Work with briefs, recover saved Markdown drafts, and review sources from your chat client.

## Connect to RoboWrite

Use the [hosted MCP endpoint](https://mcp.robowrite.ai/mcp) with Streamable HTTP and OAuth. Version 0.2.3 in this repository contains a retired server address. For a new connection, follow the current steps for your client in the [installation and usage guide](https://www.robowrite.ai/guides/robowrite-mcp#connect).

| Client | Setup instructions |
| --- | --- |
| ChatGPT | [Connect in ChatGPT](https://www.robowrite.ai/guides/robowrite-mcp#chatgpt) |
| Claude web or desktop | [Choose a connector or a plugin with skills](https://www.robowrite.ai/guides/robowrite-mcp#claude) |
| Claude Code | [Set up Claude Code](https://www.robowrite.ai/guides/robowrite-mcp#claude-code) |
| Codex | [Set up Codex](https://www.robowrite.ai/guides/robowrite-mcp#codex) |
| Cursor | [Set up Cursor](https://www.robowrite.ai/guides/robowrite-mcp#cursor) |
| Grok Build | [Set up Grok Build](https://www.robowrite.ai/guides/robowrite-mcp#grok-build) |

Already connected? Check the address on your existing RoboWrite entry. The retired entry uses host `www.robowrite.ai` and path `/api/mcp`. That address returns HTTP 410 (Gone). If both match, edit the saved server URL in place where your client supports it, keep its OAuth settings, and reconnect. If your client requires a new entry, use its setup section below or in the guide. Sign in to RoboWrite and confirm the intended workspace before opening or changing content. Tools that start research or generation can use your allowance and incur charges when overages are enabled.

Try this [first account check](https://www.robowrite.ai/guides/robowrite-mcp#first-task).

> Use RoboWrite to check my connected account and tell me which workspace is selected. Make only the read-only account call.

### Other clients with remote MCP support

For GitHub Copilot CLI, this command adds a user-level entry. Start Copilot in your own project outside the 0.2.3 plugin checkout. In a trusted project, an entry named `robowrite` in `.mcp.json` overrides the user entry. If your project defines one, edit its URL there. An unchanged 0.2.3 checkout will connect to the retired address.

```sh
copilot mcp add --transport http robowrite https://mcp.robowrite.ai/mcp
```

For a new Gemini CLI connection, merge the following `robowrite` entry into your project’s `.gemini/settings.json`. Keep any other servers in `mcpServers`. This example uses the [multi-workspace Gemini configuration](https://github.com/RoboAdApp/robowrite-plugin/blob/a1be135ff97045e0949faef28229f989d213bdc4/gemini-extension.json).

```json
{
  "mcpServers": {
    "robowrite": {
      "httpUrl": "https://mcp.robowrite.ai/mcp",
      "oauth": {
        "enabled": true,
        "clientId": "UDGKiiooDBzdYmDp",
        "redirectUri": "http://localhost:8787/oauth/callback",
        "scopes": ["robowrite:organizations:read", "robowrite:content:all_orgs", "offline_access"]
      }
    }
  }
}
```

Start Gemini in that project and run `/mcp auth robowrite`. Consent lets Gemini list your eligible workspaces, read and manage content according to your role in workspaces you have access to now or join later, and stay connected between sessions. Run one sign-in at a time on port 8787, then try the read-only account check above. If RoboWrite asks for a workspace, choose one in chat and repeat the check.

If you already have a working single-workspace connection, keep its settings. To opt into workspace switching, update its scopes to the list above and reconnect to grant access. End-to-end Gemini sign-in still needs a live test. [Gemini CLI MCP setup](https://geminicli.com/docs/tools/mcp-server/)

In VS Code, merge this entry into the `servers` object of your MCP configuration:

```json
{
  "robowrite": { "type": "http", "url": "https://mcp.robowrite.ai/mcp" }
}
```

In Windsurf, merge this entry into the `mcpServers` object of your MCP configuration:

```json
{
  "robowrite": { "serverUrl": "https://mcp.robowrite.ai/mcp" }
}
```

These examples configure the hosted address. Use the account check above to confirm that sign-in works in your client.

## What the 0.2.3 package contains

The bundled connection files and the Official MCP Registry entry for 0.2.3 still point to the retired address. For a working connection, use the [current setup instructions](https://www.robowrite.ai/guides/robowrite-mcp#connect).

- Cursor plugin metadata explicitly selects the remote MCP connection in `mcp.json`.
- Claude Code plugin metadata and a remote MCP connection in `.mcp.json` (static public PKCE client, local callback port 8787).
- Grok Build metadata in `.grok-plugin/plugin.json` pointing at URL-only `mcp.grok.json`.
- Codex metadata in `.codex-plugin/plugin.json` pointing at URL-only `mcp.codex.json`, plus `.agents/plugins/marketplace.json`.
- Gemini CLI extension metadata in `gemini-extension.json` (static public PKCE client, local callback port 8787).
- Official MCP Registry metadata for `ai.robowrite/mcp` in `server.json`.
- One shared [content workflow skill](skills/robowrite-content-ops/SKILL.md).
- The RoboWrite product mark and [MIT license](LICENSE).

The [0.2.3 release notes and historical verification matrix](https://github.com/RoboAdApp/robowrite-plugin/blob/v0.2.3/README.md#verification-matrix) document the original installation tests. The hosted service supplies the tool catalog. Bundled skills follow the plugin version installed in your client.

## Find and resume work

This version requires the hosted connector's inventory/recovery tools. After upgrading, refresh the client tool catalog and confirm `list_content`, `list_briefs`, `get_brief`, `get_content`, `list_jobs` and `get_topic_content` are available. If a tool is missing, check the server address and refresh the tool list. Recovering a saved draft uses read-only calls. Starting a new generation can consume allowance.

Try these prompts:

> Show me this month's drafts about content briefs for my selected brand, with their titles, saved versions and job status.

> Find my recent failed or unfinished RoboWrite jobs and show any drafts already saved. Do not restart generation.

> Read this draft's saved scoring, sources, assertion provenance and compliance findings.

The tools filter on the server before pagination. Briefs record their originating topic; converted means a brief was created, not that generation succeeded. The latest job attempt and the job that produced a saved version are separate. Property and brief creation require a brand ID, and MCP property creation defaults to draft-only.

## Content workflow

Ask RoboWrite to inspect an existing brand or analyze your website. Review its brand voice suggestions, choose a pillar and topic, and approve the brief before starting generation. The skill tracks resource and job IDs, uses stable idempotency keys for supported writes, and checks the stored Markdown before reporting a finished draft. It stops when strategy generation returns no usable saved pillars.

Start with a read-only review:

> Read my existing brand voice and propose a content brief for my audience. Do not save or change anything yet.

After reviewing the plan, request the draft workflow:

> Use my website to propose a brand voice and content brief for my intended audience. Let me review them before you create a draft-only property or start generation. Save the final draft in RoboWrite and show me the stored Markdown.

## Releasing

CI validates every manifest on each pull request: JSON structure, one shared version across `server.json`, the four `plugin.json` files, and `gemini-extension.json`, the hosted MCP URL, and `server.json` against the registry schema. Run the same check locally with `python3 scripts/validate_manifests.py`.

On 0.2.3, `python3 scripts/smoke_test.py` targets the retired endpoint identified above and reports HTTP 410 (Gone). [PR #23](https://github.com/RoboAdApp/robowrite-plugin/pull/23) tracks migration of the bundled configuration and smoke test. It is read-only and unauthenticated: it checks OAuth discovery, that unsigned `initialize` and `tools/list` succeed, that `tools/call` still returns 401 with an OAuth challenge, and that the static client and redirect URI in each manifest that ships one (`.mcp.json`, `mcp.json`, `gemini-extension.json`) reach the sign-in page. The URL-only Grok and Codex manifests have no client to check. A rejected client or redirect fails the build. Client ID Metadata Document support is reported as a warning if a known-good document is not accepted; `--strict` turns warnings into failures.

The next release is held for the endpoint migration in PR #23, successful installation, signup and reconnect checks, and separate publication approval. The current 0.2.3 workflow works as follows:

1. The release workflow runs on every push to `main` and reads the version from `server.json`.
2. If that version is already in the registry and has a GitHub release, it stops. A merge that does not bump the version does not start a new release; it can still finish a half-published one.
3. It checks the registry and the GitHub release separately. If the registry lacks this version, it publishes `server.json` through DNS authentication for `robowrite.ai` and confirms the registry serves it. If the release is missing, it then creates the `vX.Y.Z` tag and GitHub release on that commit. A half-finished release is completed on the next push or re-run.

A failed run can be re-run safely: a version already in the registry is not published twice. The signing key lives in the `MCP_REGISTRY_PRIVATE_KEY` secret on the `mcp-registry` environment, which only `main` can use; its public half is a TXT record on the `robowrite.ai` apex.

## License and support

The files in this plugin repository are licensed under the [MIT license](LICENSE), copyright 2026 M Powered Ventures. The license does not grant access to the hosted RoboWrite service or its private implementation.

Privacy: [RoboWrite privacy policy](https://www.robowrite.ai/privacy).

Support: [RoboWrite contact](https://www.robowrite.ai/contact), [hello@robowrite.ai](mailto:hello@robowrite.ai). Field details: [API reference](https://www.robowrite.ai/api/reference) and [integration guide](https://www.robowrite.ai/llms-full.txt).
