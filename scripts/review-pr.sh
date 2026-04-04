#!/usr/bin/env bash
# review-pr.sh — Gemini CLI headless PR review (non-API / subscription mode)
#
# Verified with Gemini CLI 0.36.0 — always re-check locally: gemini --help ; gemini --version
#
# CLI reference (headless / automation):
#   -p, --prompt   Non-interactive prompt; stdin is appended (use stdin for the git diff).
#   -o, --output-format   text | json | stream-json  (JSON + review.md extraction when using --json)
#
# Usage:
#   ./scripts/review-pr.sh [PR_ID] [--json]
#   ./scripts/review-pr.sh --json [PR_ID]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unset GEMINI_API_KEY || true

JSON_OUT=0
PR_ID="449"
for arg in "$@"; do
  if [[ "${arg}" == "--json" ]]; then
    JSON_OUT=1
  elif [[ "${arg}" =~ ^[0-9]+$ ]]; then
    PR_ID="${arg}"
  fi
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
  echo "Generating diff ..."
  python3 "${REPO_ROOT}/scripts/lib/pr_diff.py" "${META_PATH}" "${GIT_DIR}" "${DIFF_OUT}"
} 2>&1 | tee -a "${LOG}"

if [[ ! -s "${DIFF_OUT}" ]]; then
  echo "Warning: ${DIFF_OUT} is empty — check base_ref/head_ref and fetch steps in meta.json" >&2
fi

PROMPT_TEXT=$(cat "${PROMPT_SYSTEM}" "${PROMPT_GEM}" "${PROMPT_RUBRIC}")

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
