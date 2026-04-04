#!/usr/bin/env bash
# Standalone: verify local meta diff refs match GitCode PR API SHAs (needs GITCODE_TOKEN).
# Usage: ./scripts/check-pr-refs.sh [PR_ID]
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PR_ID="${1:-449}"
META_PATH="${REPO_ROOT}/workspace/inputs/pr-${PR_ID}/meta.json"
GIT_DIR="${REPO_ROOT}/workspace/pr-${PR_ID}/repo"
exec python3 "${REPO_ROOT}/scripts/lib/check_pr_refs.py" --meta "${META_PATH}" --git-dir "${GIT_DIR}"
