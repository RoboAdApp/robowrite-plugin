#!/usr/bin/env bash
# Report which parts of the release for the version in server.json already exist.
#
# Prints three key=value lines, suitable for $GITHUB_OUTPUT:
#   version=X.Y.Z
#   published=true|false   the Official MCP Registry serves this version
#   released=true|false    the GitHub release vX.Y.Z exists
#
# Checks the registry and the release independently, so a partial release (for
# example a publish without a release, or a manual tag) is still repaired.
# Needs curl, jq and an authenticated gh. Exits non-zero when a lookup fails,
# rather than guessing.
set -euo pipefail
cd "$(dirname "$0")/.."

name=$(jq -r .name server.json)
version=$(jq -r .version server.json)
repo=${GITHUB_REPOSITORY:-$(gh repo view --json nameWithOwner -q .nameWithOwner)}

found=$(curl -fsSL --get "https://registry.modelcontextprotocol.io/v0/servers" \
	--data-urlencode "search=${name}" --data-urlencode "version=${version}" \
	| jq --arg name "$name" --arg version "$version" \
		'[(.servers // [])[] | select(.server.name == $name and .server.version == $version)] | length')
if ! [[ "$found" =~ ^[0-9]+$ ]]; then
	echo "registry lookup did not return a count (got '${found}')" >&2
	exit 1
fi

if lookup=$(gh release view "v${version}" --repo "$repo" --json tagName 2>&1); then
	released=true
elif [[ "$lookup" == *"release not found"* ]]; then
	released=false
else
	echo "GitHub release lookup failed: ${lookup}" >&2
	exit 1
fi

echo "version=${version}"
echo "published=$([ "$found" -gt 0 ] && echo true || echo false)"
echo "released=${released}"
