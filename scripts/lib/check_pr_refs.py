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


def git_merge_base(git_dir: str, ref1: str, ref2: str) -> str | None:
    """Return the merge-base of two refs, or None if not related."""
    p = subprocess.run(
        ["git", "merge-base", ref1, ref2],
        cwd=git_dir,
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        return None
    return p.stdout.strip()


def git_commit_exists(git_dir: str, sha: str) -> bool:
    """Check if a commit exists locally."""
    p = subprocess.run(
        ["git", "cat-file", "-t", sha],
        cwd=git_dir,
        capture_output=True,
        text=True,
    )
    return p.returncode == 0


def git_fetch_branch(git_dir: str, remote: str, branch: str) -> bool:
    """Fetch a branch or tag from a remote. Returns True if successful."""
    # Try branch first (refs/heads/), then tag (refs/tags/)
    for ref_type in ["refs/heads/", "refs/tags/"]:
        p = subprocess.run(
            ["git", "fetch", remote, f"{ref_type}{branch}:refs/remotes/{remote}/{branch}"],
            cwd=git_dir,
            capture_output=True,
            text=True,
        )
        if p.returncode == 0:
            return True
    return False


def git_update_meta_base_ref(meta_path: str, new_base_ref: str) -> bool:
    """Update meta.json's diff.base_ref. Returns True if successful."""
    try:
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        if meta.get("diff", {}).get("base_ref") == new_base_ref:
            return True  # Already correct
        meta["diff"]["base_ref"] = new_base_ref
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"check_pr_refs: ERROR — failed to update meta.json: {e}", file=sys.stderr)
        return False


def git_branch_contains(git_dir: str, ref: str, commit: str) -> bool:
    """Check if commit is an ancestor of ref (i.e., ref contains commit)."""
    p = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, ref],
        cwd=git_dir,
        capture_output=True,
        text=True,
    )
    return p.returncode == 0


def find_local_ref_for_sha(git_dir: str, sha: str, ref_hint: str | None = None) -> str | None:
    """Find a local ref that points to the given SHA, optionally matching a ref hint."""
    # First try the hint if provided
    if ref_hint:
        p = subprocess.run(
            ["git", "rev-parse", ref_hint],
            cwd=git_dir,
            capture_output=True,
            text=True,
        )
        if p.returncode == 0 and p.stdout.strip() == sha:
            return ref_hint

    # Search for any ref (branch/tag) pointing to this SHA
    p = subprocess.run(
        ["git", "show-ref", "--hash", sha],
        cwd=git_dir,
        capture_output=True,
        text=True,
    )
    if p.returncode == 0:
        # show-ref outputs "sha ref" for each matching ref - get just the first match's ref
        pass

    # Fallback: iterate refs to find one matching the SHA
    p = subprocess.run(
        ["git", "for-each-ref", "--format=%(objectname) %(refname)", "refs/heads/", "refs/tags/"],
        cwd=git_dir,
        capture_output=True,
        text=True,
    )
    if p.returncode == 0:
        for line in p.stdout.strip().split("\n"):
            if line:
                parts = line.split(" ", 1)
                if len(parts) == 2 and parts[0] == sha:
                    return parts[1]
    return None


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
        # Check if API's base SHA exists locally at all
        api_base_exists_locally = git_commit_exists(git_dir, sb)
        # Check if API's base SHA exists locally under a ref matching the API's base.ref hint
        local_ref_for_api_base = find_local_ref_for_sha(git_dir, sb, rb if rb else None) if api_base_exists_locally else None
        # Check if the API's base SHA is an ancestor of (contained in) the local base,
        # which would indicate the local branch contains the API's base (e.g., reviewing
        # master which includes the 0.8.1 branch that the PR targets).
        api_base_in_local = git_branch_contains(git_dir, local_base, sb) if api_base_exists_locally else False

        if not api_base_exists_locally:
            # Try to fetch the base branch from origin
            print(
                f"check_pr_refs: INFO — API base sha {sb[:12]} not found locally, attempting to fetch base branch {rb} from origin...",
                file=sys.stderr,
            )
            if rb and git_fetch_branch(git_dir, "origin", rb):
                # Re-check after fetch
                api_base_exists_locally = git_commit_exists(git_dir, sb)
                local_ref_for_api_base = find_local_ref_for_sha(git_dir, sb, rb) if api_base_exists_locally else None
                api_base_in_local = git_branch_contains(git_dir, local_base, sb) if api_base_exists_locally else False
                if api_base_exists_locally:
                    print(
                        f"check_pr_refs: INFO — successfully fetched base branch {rb}, base sha {sb[:12]} now available.",
                        file=sys.stderr,
                    )
                else:
                    print(
                        f"check_pr_refs: ERROR — API base sha {sb[:12]} still not found after fetching branch {rb}.",
                        file=sys.stderr,
                    )
                    err = 1
            else:
                print(
                    f"check_pr_refs: ERROR — API base sha {sb[:12]} does not exist locally and failed to fetch base branch ({rb}) from origin.",
                    file=sys.stderr,
                )
                err = 1
        elif local_ref_for_api_base or api_base_in_local:
            ref_info = f" (found as {local_ref_for_api_base})" if local_ref_for_api_base else ""
            contain_info = " (local base contains API base)" if api_base_in_local else ""
            print(
                f"check_pr_refs: WARNING — local base {base_ref!r} is {local_base[:12]} "
                f"but API expects base sha {sb[:12]}; refs differ but SHAs are related.{ref_info}{contain_info}",
                file=sys.stderr,
            )
            # Don't set err=1 — this is a valid scenario when reviewing from a different branch
            # that contains the API's base (e.g., reviewing master which includes 0.8.1).
        elif api_base_exists_locally:
            # API's base SHA exists locally but not as a ref and not as an ancestor.
            # This happens when the PR was branched from an older release (e.g., 0.8.1)
            # and the base commit was fetched as part of the PR head, but origin/master
            # has since advanced past the branch point.
            # Fix: fetch the correct base branch and update meta.json.
            new_base_ref = f"origin/{rb}" if rb else None
            if new_base_ref and rb:
                print(
                    f"check_pr_refs: INFO — fetching base branch {new_base_ref} from origin...",
                    file=sys.stderr,
                )
                if git_fetch_branch(git_dir, "origin", rb):
                    print(
                        f"check_pr_refs: INFO — successfully fetched {new_base_ref}, updating meta.json...",
                        file=sys.stderr,
                    )
                    if git_update_meta_base_ref(args.meta, new_base_ref):
                        print(
                            f"check_pr_refs: INFO — updated meta.json base_ref to {new_base_ref!r}; "
                            f"diff needs regeneration (exit 3).",
                            file=sys.stderr,
                        )
                        sys.exit(3)  # Signal: meta updated, regenerate diff
                    else:
                        print(
                            f"check_pr_refs: ERROR — failed to update meta.json",
                            file=sys.stderr,
                        )
                        err = 1
                else:
                    print(
                        f"check_pr_refs: ERROR — failed to fetch base branch {new_base_ref}",
                        file=sys.stderr,
                    )
                    err = 1
            else:
                print(
                    f"check_pr_refs: WARNING — local base {base_ref!r} is {local_base[:12]} "
                    f"but API expects base sha {sb[:12]}; API base exists locally as floating commit "
                    f"(PR was branched from older base {rb}, diff is valid using actual merge-base).",
                    file=sys.stderr,
                )
        else:
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
