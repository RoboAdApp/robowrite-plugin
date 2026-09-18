# RoboWrite

Find and resume content work, or turn a website and reviewed brand voice into a content strategy, approved brief, and saved Markdown draft through RoboWrite's hosted MCP service.

Version 0.2.2 adds a Gemini CLI extension manifest and connection notes for GitHub Copilot CLI, VS Code, and Windsurf. Version 0.2.1 added Grok Build, Codex, and Official MCP Registry manifests. Neither claims marketplace acceptance. Cursor CLI `2026.09.02-c22c1a3` sign-in and account access have been verified through project MCP configuration. Packaged plugin and skill discovery reach the authentication step in Cursor CLI `2026.09.10-fd3934a`; packaged sign-in/account access still require verification. Claude Code 2.1.263 sign-in, account access, plugin discovery, and skill discovery have also been verified. The complete saved-draft workflow still requires verification. The authorization server now accepts Client ID Metadata Documents, so hosts that support them can sign in without a pre-registered client; dynamic client registration stays off. Grok Build, ChatGPT/Codex, Gemini CLI, Copilot, VS Code, and Windsurf sign-in are not yet verified. No plugin library listing or acceptance is claimed.

## What is included

- Cursor plugin metadata explicitly selects the remote MCP connection in `mcp.json`.
- Claude Code plugin metadata and a remote MCP connection in `.mcp.json` (static public PKCE client, local callback port 8787).
- Grok Build metadata in `.grok-plugin/plugin.json` pointing at URL-only `mcp.grok.json`.
- Codex metadata in `.codex-plugin/plugin.json` pointing at URL-only `mcp.codex.json`, plus `.agents/plugins/marketplace.json`.
- Gemini CLI extension metadata in `gemini-extension.json` (static public PKCE client, local callback port 8787).
- Official MCP Registry metadata in `server.json`, published as [`ai.robowrite/mcp`](https://registry.modelcontextprotocol.io/v0/servers?search=ai.robowrite/mcp). A registry row is not a marketplace listing.
- One shared [content workflow skill](skills/robowrite-content-ops/SKILL.md).
- The RoboWrite product mark and [MIT license](LICENSE).

The plugin connects to `https://www.robowrite.ai/api/mcp`. There is no local server to build or npm package to install.

## Verification matrix

| Client | Discovery | Browser sign-in | `get_account` | Saved draft |
| --- | --- | --- | --- | --- |
| Claude Code 2.1.263 via `--plugin-dir` | Verified | Verified | Verified | Not verified |
| Cursor CLI project `.cursor/mcp.json` | Verified | Verified | Verified | Not verified |
| Cursor CLI packaged `--plugin-dir` | Reaches requires-auth | Not verified | Not verified | Not verified |
| Grok Build | Manifest added | Not verified | Not verified | Not verified |
| ChatGPT / Codex | Manifest added | Not verified | Not verified | Not verified |
| Gemini CLI | Manifest added | Not verified | Not verified | Not verified |
| GitHub Copilot CLI 1.0.61 | Plugin and skill install verified; workspace `.mcp.json` parses | Not verified | Not verified | Not verified |
| VS Code / Windsurf | Configuration documented | Not verified | Not verified | Not verified |

## Connect

You need a RoboWrite account, the intended organization, and available allowance for requested content generation. Generation starts real work, consumes allowance, and may incur usage charges when your account permits overages. Start with account discovery before requesting a draft.

For Claude Code, from this plugin directory:

```sh
claude --plugin-dir .
```

Open `/mcp`, select the RoboWrite connection, and follow browser sign-in. The local callback uses port 8787; make sure another sign-in process is not using that port. Verify that `/robowrite:robowrite-content-ops` is available. This launch method is documented by [Claude Code](https://code.claude.com/docs/en/plugins#test-your-plugins-locally); Claude Code 2.1.263 sign-in and the read-only account check have been verified; the content workflow still requires verification.

For Cursor CLI, load this plugin directory into the project you want to use:

```sh
cursor-agent --workspace /absolute/path/to/your-project --plugin-dir /absolute/path/to/robowrite-plugin
```

Open `/mcp list` to find `Robowrite (plugin)` and its authentication status. The `/robowrite-content-ops` skill should also appear in the command menu. Packaged discovery has been verified; completing browser authentication and the account call through this packaged path remains a separate pending check. Only one sign-in process can use the local callback port 8787 at a time.

The Cursor manifest points explicitly to `mcp.json` so Cursor retains its static OAuth client configuration. In the tested Cursor CLI, automatic discovery selected Claude Code's `.mcp.json` first and reported that the auth server does not support dynamic client registration. Keep the client-specific files separate. The bundle follows the [Cursor plugin layout](https://cursor.com/docs/reference/plugins).

The previously verified Cursor project setup is also available: merge the `robowrite` entry from `mcp.json` into your project's `.cursor/mcp.json`, preserving other entries, and copy `skills/robowrite-content-ops/` to that project's `.cursor/skills/`. Enable the server and complete browser sign-in.

For Grok Build, from this plugin directory:

```sh
grok plugin install --trust .
```

Grok loads `mcp.grok.json` through `.grok-plugin/plugin.json`. That file is URL-only so Grok can run its own OAuth discovery. It does not embed the Claude/Cursor static client ID or callback port 8787. Hosted sign-in on Grok is not yet verified; if the auth server rejects dynamic registration, record that on the auth tracking issue rather than adding a static client here.

For Codex CLI, add this repository as a marketplace and install `robowrite`. Codex OAuth against Clerk is not yet verified.

For Gemini CLI:

```sh
gemini extensions install https://github.com/RoboAdApp/robowrite-plugin
```

Gemini CLI does not read Client ID Metadata Documents and falls back to dynamic client registration, which this service does not offer. `gemini-extension.json` therefore names the same static public client as Claude Code and Cursor. Gemini CLI only listens on the `/oauth/callback` path, so the redirect is `http://localhost:8787/oauth/callback`. Sign-in is not yet verified on Gemini CLI. Only one sign-in process can use port 8787 at a time.

For GitHub Copilot CLI:

```sh
copilot plugin install RoboAdApp/robowrite-plugin
```

Copilot CLI 1.0.61 reads `.claude-plugin/plugin.json` and installs the skill. Run from a checkout of this repository, it also loads `.mcp.json` as a workspace server and maps the static client and callback port, with a notice that the nested `oauth` key is deprecated. Whether an installed plugin exposes its MCP server, and browser sign-in, remain unverified. To add the server directly: `copilot mcp add --transport http robowrite https://www.robowrite.ai/api/mcp`.

For VS Code, add this to `.vscode/mcp.json` or your user MCP configuration. VS Code identifies itself with a Client ID Metadata Document, so no client ID is needed:

```json
{
	"servers": {
		"robowrite": {
			"type": "http",
			"url": "https://www.robowrite.ai/api/mcp"
		}
	}
}
```

For Windsurf, add this to `~/.codeium/windsurf/mcp_config.json`:

```json
{
	"mcpServers": {
		"robowrite": {
			"serverUrl": "https://www.robowrite.ai/api/mcp"
		}
	}
}
```

Use this first prompt:

> Use RoboWrite to check the connected account and organization. Make only the read-only get_account call. Do not create or change anything.

Check the returned organization before authorizing content changes. Keep the client's normal tool approval controls enabled. Credentials belong in browser sign-in, never in chat or these files. Reconnect to change organizations or recover from an expired or revoked grant.

## Security and network

This plugin contains no executable, hooks, install scripts, or environment-variable credentials.

| Endpoint | Why |
| --- | --- |
| `https://www.robowrite.ai/api/mcp` | Hosted Streamable HTTP MCP. Every tool call goes here. |
| `https://www.robowrite.ai/.well-known/oauth-protected-resource/api/mcp` | Protected-resource metadata for OAuth discovery. |
| Clerk issuer advertised in that metadata | Browser authorization-code + PKCE. The plugin does not store tokens. |

Scopes requested by the Claude, Cursor, and Gemini configs: `user:org:read`, `robowrite:content`, `offline_access`. Publication is not requested. There are no delete or billing-management tools.

Unauthenticated calls to `/api/mcp` return 401 with an OAuth challenge. That is intentional.

## Access and usage

The connection can read and create content in the selected organization, change existing brand voice fields, and start research or generation. It is not restricted to one test brand. Offline access allows the client to renew its connection without repeating browser sign-in, subject to expiry and revocation.

Publication access is not requested. This connector has no delete tools or billing-management tools. It also has no draft-edit tool, so locally revised text must not be described as a saved RoboWrite revision. The account's allowance and overage settings still apply; OAuth does not set a separate spending limit.

## Find and resume work

This version requires the hosted connector's inventory/recovery tools. After upgrading, refresh the client tool catalog and confirm `list_content`, `list_briefs`, `get_brief`, `get_content`, `list_jobs` and `get_topic_content` are available. If they are missing, report that the hosted deployment has not caught up; do not replace a read with another generation request.

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

To release, bump the version in all six files, merge to `main`, then push a matching tag:

```
git tag vX.Y.Z && git push origin vX.Y.Z
```

The release workflow refuses a tag that is not on `main` or does not match the manifests. It then publishes `server.json` to the Official MCP Registry through DNS authentication for `robowrite.ai` and creates the GitHub release. The registry rejects a version it already holds, so every publish needs a new version. The signing key lives in the `MCP_REGISTRY_PRIVATE_KEY` secret on the `mcp-registry` environment; its public half is a TXT record on the `robowrite.ai` apex.

## License and support

The files in this plugin repository are licensed under the [MIT license](LICENSE), copyright 2026 M Powered Ventures. The license does not grant access to the hosted RoboWrite service or its private implementation.

Privacy: [RoboWrite privacy policy](https://www.robowrite.ai/privacy).

Support: [RoboWrite contact](https://www.robowrite.ai/contact), [hello@robowrite.ai](mailto:hello@robowrite.ai). Field details: [API reference](https://www.robowrite.ai/api/reference) and [integration guide](https://www.robowrite.ai/llms-full.txt).
