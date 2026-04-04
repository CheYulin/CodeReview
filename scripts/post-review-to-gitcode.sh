#!/usr/bin/env bash
# Post results/pr-<id>/review.md to GitCode PR as an API comment.
#
# Requires: GITCODE_TOKEN (or GITCODE_PRIVATE_TOKEN) — personal access token with PR comment scope.
# Optional: GITCODE_API_BASE_URL (default https://api.gitcode.com)
#
# Usage:
#   export GITCODE_TOKEN=xxxx
#   ./scripts/post-review-to-gitcode.sh 449
#   ./scripts/post-review-to-gitcode.sh 449 --dry-run
#   ./scripts/post-review-to-gitcode.sh --no-banner 449
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "${REPO_ROOT}/scripts/lib/post_gitcode_comment.py" "$@"
