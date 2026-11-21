# RoboWrite

Plan SEO and GEO content using keyword research, competitor research, your brand voice and relevant material from your RoboWrite knowledge library. Work with briefs, recover saved Markdown drafts, and review sources from your chat client.

## Connect to RoboWrite

Use the hosted MCP server at `https://mcp.robowrite.ai/mcp` with Streamable HTTP and OAuth. Version 0.2.3 in this repository contains a retired server address. For a new connection, follow the current steps for your client in the [installation and usage guide](https://www.robowrite.ai/guides/robowrite-mcp#connect).

| Client | Setup instructions |
| --- | --- |
| ChatGPT | [Connect in ChatGPT](https://www.robowrite.ai/guides/robowrite-mcp#chatgpt) |
| Claude web or desktop | [Choose a connector or a plugin with skills](https://www.robowrite.ai/guides/robowrite-mcp#claude) |
| Claude Code | [Set up Claude Code](https://www.robowrite.ai/guides/robowrite-mcp#claude-code) |
| Codex | [Set up Codex](https://www.robowrite.ai/guides/robowrite-mcp#codex) |
| Cursor | [Set up Cursor](https://www.robowrite.ai/guides/robowrite-mcp#cursor) |
| Grok Build | [Set up Grok Build](https://www.robowrite.ai/guides/robowrite-mcp#grok-build) |

Already connected? Check the address on your existing RoboWrite entry. If it uses the retired address, follow your client's migration steps in the guide. Sign in to RoboWrite and confirm the intended workspace before opening or changing content. Tools that start research or generation can use your allowance and incur charges when overages are enabled.

Try this [first account check](https://www.robowrite.ai/guides/robowrite-mcp#first-task).

> Use RoboWrite to check my connected account and tell me which workspace is selected. Make only the read-only account call.

### Other clients with remote MCP support

For a new GitHub Copilot CLI connection:

```sh
copilot mcp add --transport http robowrite https://mcp.robowrite.ai/mcp
```

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

- Cursor plugin metadata explicitly selects the remote MCP connection in `mcp.json`.
- Claude Code plugin metadata and a remote MCP connection in `.mcp.json` (static public PKCE client, local callback port 8787).
- Grok Build metadata in `.grok-plugin/plugin.json` pointing at URL-only `mcp.grok.json`.
- Codex metadata in `.codex-plugin/plugin.json` pointing at URL-only `mcp.codex.json`, plus `.agents/plugins/marketplace.json`.
- Gemini CLI extension metadata in `gemini-extension.json` (static public PKCE client, local callback port 8787).
- Official MCP Registry metadata in `server.json`, published as [`ai.robowrite/mcp`](https://registry.modelcontextprotocol.io/v0/servers?search=ai.robowrite/mcp). A registry row is not a marketplace listing.
- One shared [content workflow skill](skills/robowrite-content-ops/SKILL.md).
- The RoboWrite product mark and [MIT license](LICENSE).

The [0.2.3 release notes and historical verification matrix](https://github.com/RoboAdApp/robowrite-plugin/blob/v0.2.3/README.md#verification-matrix) document the original installation tests. The hosted service supplies the tool catalog. Bundled skills follow the plugin version installed in your client.

## Find and resume work

This version requires the hosted connector's inventory/recovery tools. After upgrading, refresh the client tool catalog and confirm `list_content`, `list_briefs`, `get_brief`, `get_content`, `list_jobs` and `get_topic_content` are available. If a tool is missing, check the server address and refresh the tool list before trying again.

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

CI also smoke-tests the hosted service with `python3 scripts/smoke_test.py`. It is read-only and unauthenticated: it checks OAuth discovery, that unsigned `initialize` and `tools/list` succeed, that `tools/call` still returns 401 with an OAuth challenge, and that the static client and redirect URI in each manifest that ships one (`.mcp.json`, `mcp.json`, `gemini-extension.json`) reach the sign-in page. The URL-only Grok and Codex manifests have no client to check. A rejected client or redirect fails the build. Client ID Metadata Document support is reported as a warning if a known-good document is not accepted; `--strict` turns warnings into failures.

To release, bump the version in all six files and merge to `main`. Nothing else is needed:

1. The release workflow runs on every push to `main` and reads the version from `server.json`.
2. If that version is already in the registry and has a GitHub release, it stops. A merge that does not bump the version does not start a new release; it can still finish a half-published one.
3. It checks the registry and the GitHub release separately. If the registry lacks this version, it publishes `server.json` through DNS authentication for `robowrite.ai` and confirms the registry serves it. If the release is missing, it then creates the `vX.Y.Z` tag and GitHub release on that commit. A half-finished release is completed on the next push or re-run.

A failed run can be re-run safely: a version already in the registry is not published twice. The signing key lives in the `MCP_REGISTRY_PRIVATE_KEY` secret on the `mcp-registry` environment, which only `main` can use; its public half is a TXT record on the `robowrite.ai` apex.

## License and support

The files in this plugin repository are licensed under the [MIT license](LICENSE), copyright 2026 M Powered Ventures. The license does not grant access to the hosted RoboWrite service or its private implementation.

Privacy: [RoboWrite privacy policy](https://www.robowrite.ai/privacy).

Support: [RoboWrite contact](https://www.robowrite.ai/contact), [hello@robowrite.ai](mailto:hello@robowrite.ai). Field details: [API reference](https://www.robowrite.ai/api/reference) and [integration guide](https://www.robowrite.ai/llms-full.txt).
