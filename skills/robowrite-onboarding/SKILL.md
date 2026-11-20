---
name: robowrite-onboarding
description: Guide a new RoboWrite user from signup or first connection to their first brand and content task. Use when someone asks how to get started, onboard a workspace, or resume unfinished brand onboarding.
---

# Get started with RoboWrite

Ask what the user wants to accomplish first, unless they already told you. A first useful result might be finding an existing brief, reading a brand voice, or outlining a first article in chat.

**Connect and choose a workspace.** If the user needs an account, direct them to [RoboWrite](https://www.robowrite.ai/app) to sign up and create or join their workspace. Use the bundled `robowrite-setup` skill for browser sign-in, reconnect, and workspace selection. Keep credentials in the browser. Confirm the workspace with a successful `get_account` before reading its content. For a multi-workspace connection, pass the confirmed `organization_id` on every subsequent call. An existing workspace-bound grant keeps its original target. If the user switches workspaces, verify the new account and clear the previous brand and setup IDs.

**Start from what is already there.** Use the account’s brands and, if needed, page through `list_brands`. When several brands fit, ask which one to use. Read the selected brand with `get_brand`. Offer one read-only first task tied to the user’s goal, such as finding a saved brief or reviewing the brand voice. Use `robowrite-content-ops` when the user chooses an editorial task.

**Resume existing onboarding first.** If the user already started website research, recover the setup ID from the original start response and call `get_brand_setup` in that workspace. The job ID identifies the background job. If the setup ID is missing, look for the original response or resume in the app. Keep the existing operation key and exact inputs for any retry. If you cannot identify the setup, report what is missing and stop before starting new research.

**Use the web wizard for manual entry.** Open [RoboWrite](https://www.robowrite.ai/app) and have the user check the active workspace in the web app against the one confirmed in chat. Selecting a workspace in chat does not switch the browser. If they differ, use the workspace picker in the main RoboWrite app before opening the wizard. If the user cannot verify the workspace, stop before entering, resuming, or saving brand details. In the [onboarding wizard](https://www.robowrite.ai/app/onboarding), resume the existing setup or choose **Manual** for a new brand without website research. Re-read the selected workspace’s brands after the save.

**Start new website research only when requested.** For an empty workspace, offer manual entry or website-assisted setup. Confirm the site, explain that `start_brand_setup` starts external work and can use account allowance, and get explicit approval for that work and any potential charge. Retain its operation key, exact input, setup ID and job ID.

Use `get_brand_setup` to follow the same setup. For pending or running research, report progress and check again later. For a failure, report the error. When ready, present the proposed brand and voice for review, invite edits, and ask before saving with `confirm_brand_setup`. Use a separate stable confirmation key. If the confirmation response is lost, read the setup again. When its status is `confirmed`, read the returned `brand_id` with `get_brand` and continue with the saved brand. Retry an uncertain write only with the same key and inputs.

End with the verified workspace and brand, or the exact step still pending. Propose one next action. Starting generation, buying a plan, or publishing requires a separate user decision.
