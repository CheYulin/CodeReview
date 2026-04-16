#!/usr/bin/env bash
# Post the latest PR review markdown to GitCode as an API comment.
#
# Default review file (no extra args): results/pr-<id>/review.md if present (usually a symlink
# to the latest review-<timestamp>.md from review-pr.sh); otherwise the newest review-*.md by
# mtime. Use --review only when you want a specific file.
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
