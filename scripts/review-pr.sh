#!/usr/bin/env bash
# review-pr.sh — Gemini CLI headless PR review (non-API / subscription mode)
#
# Verified with Gemini CLI 0.36.0 — always re-check locally: gemini --help ; gemini --version
#
# CLI reference (headless / automation):
#   -p, --prompt   Non-interactive prompt; stdin is appended (use stdin for the diff).
#   -o, --output-format   text | json | stream-json  (JSON + review.md extraction when using --json)
#
# Usage:
#   ./scripts/review-pr.sh [PR_ID] [--json]
#   ./scripts/review-pr.sh 470 --issues 234,233,235
#   ./scripts/review-pr.sh --pr 470 --issues 234,235 [--rfcs 'https://doc/a|https://doc/b'] [--json]
#   ./scripts/review-pr.sh --help
#
# If GITCODE_TOKEN is set, after generating diff the script compares API base/head SHAs with
# local meta diff refs (set CODE_REVIEW_SKIP_PR_CHECK=1 or --no-pr-check to skip).
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  ./scripts/review-pr.sh [PR_ID] [--issues N[,N...]] [--rfcs 'URL|URL...'] [--json] [--no-pr-check]

Arguments:
  PR_ID           Pull request number (folder workspace/pr-<id>, default 449 if omitted)
  --issues        Comma-separated GitCode issue numbers; written to meta related.issues + closes
  --rfcs          Pipe-separated RFC/design doc URLs (use | between URLs)
  --pr            Same as positional PR_ID (if you prefer flags)
  --json          Also write review.json from Gemini
  --no-pr-check   Skip GitCode API vs local git ref SHA check
  -h, --help      Show this help

Environment:
  GITCODE_TOKEN   If set, verify PR base/head SHAs match local diff refs (after git fetch)

Examples:
  ./scripts/review-pr.sh 449 --issues 234,233,235
  ./scripts/review-pr.sh 470 --issues 234 --rfcs 'https://example.com/rfc.md'
USAGE
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unset GEMINI_API_KEY || true

JSON_OUT=0
PR_ID="449"
ISSUES_CSV=""
RFCS_PSV=""
NO_PR_CHECK=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --json)
      JSON_OUT=1
      shift
      ;;
    --no-pr-check)
      NO_PR_CHECK=1
      shift
      ;;
    --issues)
      ISSUES_CSV="${2:-}"
      shift 2
      ;;
    --rfcs)
      RFCS_PSV="${2:-}"
      shift 2
      ;;
    --pr)
      PR_ID="${2:-449}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      if [[ "$1" =~ ^[0-9]+$ ]]; then
        PR_ID="$1"
      else
        echo "Unknown argument: $1" >&2
        usage >&2
        exit 1
      fi
      shift
      ;;
  esac
done

META_PATH="${REPO_ROOT}/workspace/inputs/pr-${PR_ID}/meta.json"
# Prompt = 业务上下文 + Gem 行为 + 证据型输出细则（与网页 Gems 对齐）
PROMPT_SYSTEM="${REPO_ROOT}/assets/prompts/system-pr-449.md"
PROMPT_GEM="${REPO_ROOT}/assets/gems/yuanrong-pr-review/GEM.md"
PROMPT_RUBRIC="${REPO_ROOT}/assets/prompts/review-evidence-rubric.md"
WS="${REPO_ROOT}/workspace/pr-${PR_ID}"
RESULTS="${REPO_ROOT}/results/pr-${PR_ID}"
GIT_DIR="${WS}/repo"
DIFF_OUT="${WS}/diff.patch"
LOG="${WS}/run.log"
STDERR_LOG="${RESULTS}/stderr.log"

if [[ ! -f "${META_PATH}" ]]; then
  echo "Bootstrapping ${META_PATH} (scripts/lib/bootstrap_meta.py) ..."
  python3 "${REPO_ROOT}/scripts/lib/bootstrap_meta.py" "${PR_ID}"
fi
if [[ ! -f "${META_PATH}" ]]; then
  echo "Missing ${META_PATH}" >&2
  exit 1
fi

if [[ -n "${ISSUES_CSV}" || -n "${RFCS_PSV}" ]]; then
  echo "Merging --issues / --rfcs into ${META_PATH} ..."
  MERGE_ARGS=(python3 "${REPO_ROOT}/scripts/lib/merge_meta_cli.py" --meta "${META_PATH}" --pr "${PR_ID}")
  [[ -n "${ISSUES_CSV}" ]] && MERGE_ARGS+=(--issues "${ISSUES_CSV}")
  [[ -n "${RFCS_PSV}" ]] && MERGE_ARGS+=(--rfcs "${RFCS_PSV}")
  "${MERGE_ARGS[@]}"
fi

for f in "${PROMPT_SYSTEM}" "${PROMPT_GEM}" "${PROMPT_RUBRIC}"; do
  if [[ ! -f "${f}" ]]; then
    echo "Missing ${f}" >&2
    exit 1
  fi
done

mkdir -p "${WS}" "${RESULTS}"

{
  echo "======== $(date -Iseconds) ========"
  echo "PR_ID=${PR_ID} JSON_OUT=${JSON_OUT}"
  echo "META_PATH=${META_PATH}"
  [[ -n "${ISSUES_CSV}" ]] && echo "ISSUES=${ISSUES_CSV}"
  [[ -n "${RFCS_PSV}" ]] && echo "RFCS=${RFCS_PSV}"
  echo "Generating diff ..."
  python3 "${REPO_ROOT}/scripts/lib/pr_diff.py" "${META_PATH}" "${GIT_DIR}" "${DIFF_OUT}"
} 2>&1 | tee -a "${LOG}"

if [[ ! -s "${DIFF_OUT}" ]]; then
  echo "Warning: ${DIFF_OUT} is empty — check base_ref/head_ref and fetch steps in meta.json" >&2
fi

if [[ "${NO_PR_CHECK}" -eq 0 ]] && [[ "${CODE_REVIEW_SKIP_PR_CHECK:-0}" != "1" ]] && [[ -d "${GIT_DIR}/.git" ]]; then
  echo "Checking PR base/head SHAs vs GitCode API (scripts/lib/check_pr_refs.py) ..."
  python3 "${REPO_ROOT}/scripts/lib/check_pr_refs.py" --meta "${META_PATH}" --git-dir "${GIT_DIR}" || exit $?
fi

PROMPT_TEXT=$(cat "${PROMPT_SYSTEM}" "${PROMPT_GEM}" "${PROMPT_RUBRIC}")
PROMPT_TEXT="${PROMPT_TEXT}

$(python3 "${REPO_ROOT}/scripts/lib/meta_links_prompt.py" "${META_PATH}")"

if ! command -v gemini >/dev/null 2>&1; then
  echo "gemini CLI not found in PATH" >&2
  exit 1
fi

echo "Checking Gemini CLI auth (non-API) ..."
if ! gemini whoami >/dev/null 2>&1; then
  echo "Not logged in. Run: gemini login" >&2
  exit 1
fi

echo "Running Gemini (stdin = diff; -p = system + GEM + evidence rubric) ..."
if [[ "${JSON_OUT}" -eq 1 ]]; then
  gemini -p "${PROMPT_TEXT}" --output-format json < "${DIFF_OUT}" > "${RESULTS}/review.json" 2> "${STDERR_LOG}"
  python3 - "${RESULTS}" <<'PY'
import json
import os
import sys

root = sys.argv[1]
json_path = os.path.join(root, "review.json")
md_path = os.path.join(root, "review.md")
with open(json_path, encoding="utf-8") as f:
    data = json.load(f)
text = data.get("response", data) if isinstance(data, dict) else str(data)
if not isinstance(text, str):
    text = json.dumps(text, ensure_ascii=False, indent=2)
with open(md_path, "w", encoding="utf-8") as out:
    out.write(text)
PY
  echo "Wrote ${RESULTS}/review.json and ${RESULTS}/review.md"
else
  gemini -p "${PROMPT_TEXT}" < "${DIFF_OUT}" > "${RESULTS}/review.md" 2> "${STDERR_LOG}"
  echo "Wrote ${RESULTS}/review.md"
fi

if [[ -s "${STDERR_LOG}" ]]; then
  echo "Gemini stderr captured: ${STDERR_LOG}"
fi
{
  echo "======== finished $(date -Iseconds) ========"
} >>"${LOG}"

exit 0
