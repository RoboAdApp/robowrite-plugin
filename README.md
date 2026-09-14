# RoboWrite

Find and resume content work, or turn a website and reviewed brand voice into a content strategy, approved brief, and saved Markdown draft through RoboWrite's hosted MCP service.

Version 0.2.0 adds inventory and job-recovery guidance and includes Cursor and Claude Code plugin configurations and one shared content workflow skill. Cursor CLI `2026.09.02-c22c1a3` sign-in and account access have been verified through project MCP configuration. Packaged plugin and skill discovery reach the authentication step in Cursor CLI `2026.09.10-fd3934a`; packaged sign-in/account access still require verification. Claude Code 2.1.263 sign-in, account access, plugin discovery, and skill discovery have also been verified. The complete saved-draft workflow still requires verification. Grok Bot support remains under investigation. No plugin library listing or acceptance is claimed.

## What is included

- Cursor plugin metadata explicitly selects the remote MCP connection in `mcp.json`.
- Claude Code plugin metadata and a remote MCP connection in `.mcp.json`.
- One shared [content workflow skill](skills/robowrite-content-ops/SKILL.md).
- The RoboWrite product mark and [MIT license](LICENSE).

The plugin connects to `https://www.robowrite.ai/api/mcp`. There is no local server to build or npm package to install.

## Connect

You need a RoboWrite account, the intended organization, and available allowance for requested content generation. Generation starts real work, consumes allowance, and may incur usage charges when your account permits overages. Start with account discovery before requesting a draft.

For Claude Code, from this plugin directory:

```sh
claude --plugin-dir .
```

Open `/mcp`, select the RoboWrite connection, and follow browser sign-in. The local callback uses port 8787; make sure another sign-in process is not using that port. Verify that `/robowrite:robowrite-content-ops` is available. This launch method is documented by [Claude Code](https://code.claude.com/docs/en/plugins#test-your-plugins-locally); Claude Code 2.1.263 sign-in and the read-only account check have been verified; the content workflow still requires verification.

For Cursor CLI, load this plugin directory into the project you want to use:

```sh
cursor-agent --workspace /absolute/path/to/your/project --plugin-dir /absolute/path/to/robowrite-plugin
```

Open `/mcp list` to find `Robowrite (plugin)` and its authentication status. The `/robowrite-content-ops` skill should also appear in the command menu. Packaged discovery has been verified; completing browser authentication and the account call through this packaged path remains a separate pending check. Only one sign-in process can use the local callback port 8787 at a time.

The Cursor manifest points explicitly to `mcp.json` so Cursor retains its static OAuth client configuration. In the tested Cursor CLI, automatic discovery selected Claude Code's `.mcp.json` first and reported that the auth server does not support dynamic client registration. Keep the client-specific files separate. The bundle follows the [Cursor plugin layout](https://cursor.com/docs/reference/plugins).

The previously verified Cursor project setup is also available: merge the `robowrite` entry from `mcp.json` into your project's `.cursor/mcp.json`, preserving other entries, and copy `skills/robowrite-content-ops/` to that project's `.cursor/skills/`. Enable the server and complete browser sign-in.

Use this first prompt:

> Use RoboWrite to check the connected account and organization. Make only the read-only get_account call. Do not create or change anything.

Check the returned organization before authorizing content changes. Keep the client's normal tool approval controls enabled. Credentials belong in browser sign-in, never in chat or these files. Reconnect to change organizations or recover from an expired or revoked grant.

## Access and usage

The requested scopes are `user:org:read`, `robowrite:content`, and `offline_access`. The connection can read and create content in the selected organization, change existing brand voice fields, and start research or generation. It is not restricted to one test brand. Offline access allows the client to renew its connection without repeating browser sign-in, subject to expiry and revocation.

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

## License and support

The files in this plugin repository are licensed under the [MIT license](LICENSE), copyright 2026 M Powered Ventures. The license does not grant access to the hosted RoboWrite service or its private implementation.

Privacy: [RoboWrite privacy policy](https://www.robowrite.ai/privacy).

Support: [RoboWrite contact](https://www.robowrite.ai/contact), [hello@robowrite.ai](mailto:hello@robowrite.ai). Field details: [API reference](https://www.robowrite.ai/api/reference) and [integration guide](https://www.robowrite.ai/llms-full.txt).
