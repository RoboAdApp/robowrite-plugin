---
name: robowrite-onboarding
description: Guide a new RoboWrite user from signup or first connection to their first brand and content task. Use when someone asks how to get started, onboard a workspace, or resume unfinished brand onboarding.
---

# Get started with RoboWrite

Ask what the user wants to accomplish first, unless they already told you. A first useful result might be finding an existing brief, reading a brand voice, or outlining a first article in chat.

**Connect and choose a workspace.** If the user needs an account, direct them to [RoboWrite](https://www.robowrite.ai/app) to sign up and create or join their workspace. Use the bundled `robowrite-setup` skill for browser sign-in, reconnect, and workspace selection. Keep credentials in the browser. Confirm the workspace with a successful `get_account` before reading its content. For a multi-workspace connection, pass the confirmed `organization_id` on every subsequent call. An existing workspace-bound grant keeps its original target. If the user switches workspaces, verify the new account and clear the previous brand and setup IDs.

**Start from what is already there.** Use the account’s brands and, if needed, page through `list_brands`. When several brands fit, ask which one to use. Read the selected brand with `get_brand`. Offer one read-only first task tied to the user’s goal, such as finding a saved brief or reviewing the brand voice. Use `robowrite-content-ops` when the user chooses an editorial task.

**For an empty workspace**, offer two paths. For manual entry, open the [signed-in onboarding wizard](https://www.robowrite.ai/app/onboarding) and choose **Manual** to enter brand details without starting website research. If the user already began setup in the app, resume that setup there. Once the brand is saved, re-read the workspace brands to confirm it.

For website-assisted setup, confirm the intended site and explain that `start_brand_setup` starts external research and can use account allowance. Get explicit approval for that work and any potential charge before starting. Retain its operation key, exact input, and returned setup and job IDs. If the user returns with a setup ID for this workspace, read `get_brand_setup` first. While work is pending, report its status and check the same setup later. If it fails, report the error and ask how to proceed. At ready, show the proposed brand and voice, invite edits, and ask before saving the new brand with `confirm_brand_setup`. Use a separate stable confirmation key. On an uncertain write, recover the existing result before retrying with the same inputs and key.

End with the verified workspace and brand, or the exact step still pending. Propose one next action. Starting generation, buying a plan, or publishing requires a separate user decision.
