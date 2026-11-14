---
name: robowrite-setup
description: Connect RoboWrite, confirm the authorized organization, and start with a read-only account check after installation or reconnection.
---

Connect the packaged RoboWrite MCP server through the host's browser OAuth flow. The canonical endpoint is https://mcp.robowrite.ai/mcp. Let the host manage OAuth registration and callbacks; do not give the user a hardcoded localhost callback. Never request passwords, verification codes, API keys, bearer tokens, or client secrets in chat.

Start with get_account and confirm the returned organization is the user's intended workspace. If disconnected or expired, use the host's reconnect action. Tokens for the retired endpoint do not authorize this resource. If organization setup is required, direct the user to complete their own signed-in setup; do not invent an organization or select a paid plan. Reconnect to change the authorized organization instead of substituting another organization's IDs.

After a successful account check, offer to find an existing brand, brief or saved draft. Read the current connected tool schemas. Do not start generation or change content as part of setup. Explain that generation consumes account allowance and may incur overage charges when enabled. CMS publication is not exposed by this connection.

For supported-client setup and troubleshooting, use https://www.robowrite.ai/guides/robowrite-mcp. A successful public catalog check alone does not prove user authorization or completion of setup.
