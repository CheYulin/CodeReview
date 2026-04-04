#!/usr/bin/env python3
"""Compare GitCode PR API base/head SHAs with local git refs from meta.json."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any


def parse_pr_from_meta(meta: dict[str, Any]) -> tuple[str, str, int]:
    url = str(meta.get("pr_url") or "")
    m = re.search(r"https?://[^/]+/([^/]+)/([^/]+)/pull/(\d+)", url, re.I)
    if m:
        return m.group(1), m.group(2), int(m.group(3))
    gc = meta.get("gitcode") or {}
    owner = gc.get("owner")
    repo = gc.get("repo")
    num = meta.get("pr_number")
    if owner and repo and num is not None:
        return str(owner), str(repo), int(num)
    sys.exit("meta.json: need pr_url or gitcode.owner/repo + pr_number")


def get_token() -> str:
    return (
        os.environ.get("GITCODE_TOKEN")
        or os.environ.get("GITCODE_PRIVATE_TOKEN")
        or os.environ.get("GITEA_TOKEN")
        or ""
    )


def api_base(meta: dict[str, Any]) -> str:
    gc = meta.get("gitcode") or {}
    return str(
        gc.get("api_base_url")
        or os.environ.get("GITCODE_API_BASE_URL")
        or "https://api.gitcode.com"
    ).rstrip("/")


def fetch_pr_json(owner: str, repo: str, number: int, token: str, base_url: str) -> dict[str, Any]:
    url = f"{base_url}/api/v5/repos/{owner}/{repo}/pulls/{number}"
    # GitCode accepts PRIVATE-TOKEN (GitLab-style) and/or Bearer; try both.
    header_sets: list[dict[str, str]] = []
    if token:
        header_sets = [
            {"PRIVATE-TOKEN": token},
            {"Authorization": f"Bearer {token}"},
        ]
    last_err: str | None = None
    for i, hdrs in enumerate(header_sets):
        req = urllib.request.Request(url)
        for k, v in hdrs.items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            last_err = f"HTTP {e.code}: {body[:2000]}"
            if e.code in (401, 403, 400) and i < len(header_sets) - 1:
                continue
            sys.exit(f"PR API {last_err}")
        except urllib.error.URLError as e:
            sys.exit(f"PR API request failed: {e}")
    sys.exit(f"PR API failed: {last_err or 'unknown'}")


def extract_remote_refs_and_shas(data: dict[str, Any]) -> tuple[str, str, str, str]:
    """Return base_ref, base_sha, head_ref, head_sha from API payload (best effort)."""
    # GitHub / Gitea–style
    if isinstance(data.get("base"), dict) and isinstance(data.get("head"), dict):
        b, h = data["base"], data["head"]
        return (
            str(b.get("ref") or b.get("Ref") or ""),
            str(b.get("sha") or ""),
            str(h.get("ref") or h.get("Ref") or ""),
            str(h.get("sha") or ""),
        )
    # Flat keys (some hosts)
    return (
        str(data.get("base_branch") or data.get("base_ref") or ""),
        str(data.get("base_sha") or ""),
        str(data.get("head_branch") or data.get("head_ref") or ""),
        str(data.get("head_sha") or ""),
    )


def git_rev_parse(git_dir: str, ref: str) -> str | None:
    p = subprocess.run(
        ["git", "rev-parse", ref],
        cwd=git_dir,
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        return None
    return p.stdout.strip()


def main() -> None:
    ap = argparse.ArgumentParser(description="Verify local diff refs match GitCode PR API.")
    ap.add_argument("--meta", type=str, required=True)
    ap.add_argument("--git-dir", type=str, required=True)
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Exit with error if API returns no SHAs (default: warn only)",
    )
    args = ap.parse_args()

    token = get_token()
    if not token:
        print(
            "check_pr_refs: skip (set GITCODE_TOKEN or GITCODE_PRIVATE_TOKEN to verify PR base/head against API)",
            file=sys.stderr,
        )
        sys.exit(0)

    with open(args.meta, encoding="utf-8") as f:
        meta = json.load(f)

    owner, repo, number = parse_pr_from_meta(meta)
    d = meta.get("diff") or {}
    base_ref = str(d.get("base_ref") or "")
    head_ref = str(d.get("head_ref") or "")
    if not base_ref or not head_ref:
        sys.exit("meta.json: diff.base_ref and diff.head_ref are required")

    payload = fetch_pr_json(owner, repo, number, token, api_base(meta))
    rb, sb, rh, sh = extract_remote_refs_and_shas(payload)

    git_dir = args.git_dir
    if not os.path.isdir(os.path.join(git_dir, ".git")):
        sys.exit(f"Not a git repo: {git_dir}")

    local_base = git_rev_parse(git_dir, base_ref)
    local_head = git_rev_parse(git_dir, head_ref)

    lines = [
        "check_pr_refs:",
        f"  API PR #{number}  base.ref={rb!r} head.ref={rh!r}",
        f"  API SHAs      base={sb[:12] if sb else '?'} head={sh[:12] if sh else '?'}",
        f"  meta diff     base_ref={base_ref!r} head_ref={head_ref!r}",
        f"  local SHAs    base={local_base[:12] if local_base else 'MISSING'} "
        f"head={local_head[:12] if local_head else 'MISSING'}",
    ]
    print("\n".join(lines), file=sys.stderr)

    err = 0
    if sh and local_head and sh != local_head:
        print(
            f"check_pr_refs: ERROR — local head {head_ref!r} is {local_head[:12]} "
            f"but API expects head sha {sh[:12]} (wrong fetch or stale ref).",
            file=sys.stderr,
        )
        err = 1
    if sb and local_base and sb != local_base:
        print(
            f"check_pr_refs: ERROR — local base {base_ref!r} is {local_base[:12]} "
            f"but API expects base sha {sb[:12]} (update origin or fix base_ref).",
            file=sys.stderr,
        )
        err = 1

    if not sh or not sb:
        msg = "check_pr_refs: API did not return full base/head SHAs; branch-name-only check skipped."
        if rb and rh:
            print(
                f"check_pr_refs: note — remote base.ref={rb!r} head.ref={rh!r} "
                f"(compare with your meta / fork branch names manually).",
                file=sys.stderr,
            )
        if args.strict:
            print(msg, file=sys.stderr)
            sys.exit(2)
        print(msg, file=sys.stderr)

    if err:
        sys.exit(1)
    print("check_pr_refs: OK — local refs match API SHAs for this PR.", file=sys.stderr)
    sys.exit(0)


if __name__ == "__main__":
    main()
