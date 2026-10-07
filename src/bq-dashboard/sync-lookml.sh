#!/bin/bash
# Refresh the LookML view files bundled in the app from the source-of-truth repo.
# Usage: ./sync-lookml.sh [view ...]   (default: patient_gold_latest)
set -o errexit -o nounset -o pipefail

REPO="verily-src/analytics-internal-looker"
BRANCH="${LOOKML_BRANCH:-main}"
DEST="$(dirname "$0")/app/lookml"
VIEWS=("${@:-patient_gold_latest}")

mkdir -p "${DEST}"
for view in "${VIEWS[@]}"; do
  gh api "repos/${REPO}/contents/views/${view}.view.lkml?ref=${BRANCH}" \
    -H "Accept: application/vnd.github.raw" > "${DEST}/${view}.view.lkml"
  echo "Synced ${view}.view.lkml from ${REPO}@${BRANCH}"
done
