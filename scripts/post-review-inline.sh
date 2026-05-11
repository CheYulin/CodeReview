#!/usr/bin/env bash
# Post Section E findings as line-specific comments to GitCode PR.
#
# Usage:
#   export GITCODE_TOKEN=xxxx
#   ./scripts/post-review-inline.sh 956
#   ./scripts/post-review-inline.sh 956 --dry-run
#   ./scripts/post-review-inline.sh 956 --fallback-only
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "${REPO_ROOT}/scripts/lib/post_gitcode_inline.py" "$@"
