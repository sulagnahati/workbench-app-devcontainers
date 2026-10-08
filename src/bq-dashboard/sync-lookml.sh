#!/bin/bash
# Fetch the LookML source (views, models, dashboards) into app/lookml/ from the
# source-of-truth repo. The folder is gitignored; do not commit it.
# Usage: ./sync-lookml.sh   (needs `gh auth login` with access to the repo)
set -o errexit -o nounset -o pipefail

REPO="verily-src/analytics-internal-looker"
BRANCH="${LOOKML_BRANCH:-main}"
DEST="$(cd "$(dirname "$0")" && pwd)/app/lookml"

rm -rf "${DEST}"
gh repo clone "${REPO}" "${DEST}" -- --depth 1 --branch "${BRANCH}" --quiet
rm -rf "${DEST}/.git"
echo "Synced ${REPO}@${BRANCH} into ${DEST}"
