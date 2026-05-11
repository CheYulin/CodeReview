#!/usr/bin/env python3
"""Clone upstream if needed, run meta.json fetch steps, write git diff to patch file."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any


def run(cmd: list[str], cwd: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=cwd, check=check, text=True)


def get_token() -> str:
    return (
        os.environ.get("GITCODE_TOKEN")
        or os.environ.get("GITCODE_PRIVATE_TOKEN")
        or os.environ.get("GITEA_TOKEN")
        or ""
    )


def get_api_base(meta: dict[str, Any]) -> str:
    gc = meta.get("gitcode") or {}
    return str(
        gc.get("api_base_url")
        or os.environ.get("GITCODE_API_BASE_URL")
        or "https://api.gitcode.com"
    ).rstrip("/")


def fetch_pr_info_from_api(owner: str, repo: str, pr_number: int, token: str, base_url: str) -> dict[str, Any] | None:
    """Fetch PR info from GitCode API. Returns None if token is not available."""
    if not token:
        return None
    url = f"{base_url}/api/v5/repos/{owner}/{repo}/pulls/{pr_number}"
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
            last_err = f"HTTP {e.code}: {body[:500]}"
            if e.code in (401, 403, 400) and i < len(header_sets) - 1:
                continue
            print(f"fetch_pr_info_from_api: {last_err}", flush=True)
            return None
        except urllib.error.URLError as e:
            print(f"fetch_pr_info_from_api: request failed: {e}", flush=True)
            return None
    print(f"fetch_pr_info_from_api: failed: {last_err or 'unknown'}", flush=True)
    return None


def clone_if_needed(git_dir: str, upstream: str) -> None:
    """Ensure git_dir is a clone of upstream. Existing repos are only updated, never deleted."""
    git_internal = os.path.join(git_dir, ".git")
    if os.path.isdir(git_internal):
        print("+ git fetch origin --tags  # refresh tags", flush=True)
        subprocess.run(["git", "fetch", "origin", "--tags"], cwd=git_dir, check=False)
        print("+ git fetch origin +refs/pull/*:refs/pull/* +refs/merge-requests/*:refs/merge-requests/*  # refresh PR/MR refs", flush=True)
        subprocess.run(
            ["git", "fetch", "origin", "+refs/pull/*:refs/pull/*", "+refs/merge-requests/*:refs/merge-requests/*"],
            cwd=git_dir, check=False,
        )
        subprocess.run(["git", "remote", "prune", "origin"], cwd=git_dir, check=False)
        return
    parent = os.path.dirname(git_dir.rstrip(os.sep))
    if parent:
        os.makedirs(parent, exist_ok=True)
    # Path exists but is not a repo — git clone refuses non-empty dirs (e.g. .gitkeep).
    if os.path.exists(git_dir):
        print(f"+ rm -rf {git_dir}  # not a git repo, replacing", flush=True)
        shutil.rmtree(git_dir)
    print("+ git clone <upstream> " + git_dir, flush=True)
    subprocess.run(["git", "clone", upstream, git_dir], check=True)


def ensure_remote(git_dir: str, name: str, url: str) -> None:
    p = run(["git", "remote", "get-url", name], cwd=git_dir, check=False)
    if p.returncode != 0:
        run(["git", "remote", "add", name, url], cwd=git_dir)
    else:
        run(["git", "remote", "set-url", name, url], cwd=git_dir)


def _fetch_pr_head_refspecs(pr: int, local_branch: str, override: str | None) -> list[str]:
    if override:
        return [override]
    # Prefix '+' forces update of local_branch when it diverged from a prior fetch.
    # GitHub / Gitea / some hosts; GitLab-style MR refs; GitCode often has none of these.
    lb = local_branch
    return [
        f"+refs/pull/{pr}/head:{lb}",
        f"+pull/{pr}/head:{lb}",
        f"+refs/merge-requests/{pr}/head:{lb}",
        f"+merge-requests/{pr}/head:{lb}",
    ]


def fetch_pr_head(git_dir: str, remote: str, pr: int, local_branch: str, refspec_override: str | None) -> bool:
    """Try several PR refspecs. Returns True if one succeeded."""
    for ref in _fetch_pr_head_refspecs(pr, local_branch, refspec_override):
        print("+ git fetch " + remote + " " + ref, flush=True)
        p = subprocess.run(
            ["git", "fetch", remote, ref],
            cwd=git_dir,
            capture_output=True,
            text=True,
        )
        if p.returncode == 0:
            print(f"+ ok: fetched {ref.split(':')[0]}", flush=True)
            return True
        err = (p.stderr or p.stdout or "").strip()
        if err:
            print(f"  (skip) {err.splitlines()[-1]}", flush=True)
    return False


def apply_fetch_fork_branch(git_dir: str, item: dict[str, Any]) -> None:
    rn = item["remote_name"]
    ru = item["remote_url"]
    rb = item["remote_branch"]
    lb = item["local_branch"]
    ensure_remote(git_dir, rn, ru)
    run(["git", "fetch", rn, f"+{rb}:{lb}"], cwd=git_dir)


def parse_pr_from_meta(meta: dict[str, Any]) -> tuple[str, str, int] | None:
    """Parse owner, repo, pr_number from pr_url in meta. Returns None if not found."""
    url = str(meta.get("pr_url") or "")
    m = re.search(r"https?://[^/]+/([^/]+)/([^/]+)/(?:pull|merge_requests)/(\d+)", url, re.I)
    if m:
        return m.group(1), m.group(2), int(m.group(3))
    return None


def apply_fetch(git_dir: str, item: dict[str, Any], meta: dict[str, Any]) -> None:
    t = item.get("type")
    if t == "pr_head":
        remote = item["remote"]
        pr = int(item["pr"])
        local_branch = item["local_branch"]
        override = item.get("refspec")
        ok = fetch_pr_head(git_dir, remote, pr, local_branch, override)
        if ok:
            return
        fb = meta.get("fork_fallback") or {}
        br = str(fb.get("branch", "") or "").strip()
        # If branch is a placeholder, try to fetch actual branch info from API
        if not br or "REPLACE" in br.upper():
            token = get_token()
            if token:
                parsed = parse_pr_from_meta(meta)
                if parsed:
                    owner, repo, pr_num = parsed
                    api_base = get_api_base(meta)
                    pr_data = fetch_pr_info_from_api(owner, repo, pr_num, token, api_base)
                    if pr_data:
                        head_info = pr_data.get("head", {})
                        base_info = pr_data.get("base", {})
                        api_branch = head_info.get("ref") if head_info else None
                        api_base_ref = base_info.get("ref") if base_info else None
                        head_repo = (head_info.get("repo", {}) or {}).get("html_url") if head_info else None
                        if api_branch:
                            br = api_branch
                            print(
                                f"pr_diff: fetched branch {br!r} from GitCode API "
                                f"(fork: {head_repo})",
                                flush=True,
                            )
                        if api_base_ref and api_base_ref != (fb.get("branch") or ""):
                            print(
                                f"pr_diff: fetched base branch {api_base_ref!r} from GitCode API",
                                flush=True,
                            )
                        if head_repo or api_branch:
                            fb = dict(fb)
                            if head_repo:
                                fb["remote_url"] = head_repo
                            if api_branch:
                                fb["branch"] = br
                            meta = dict(meta)
                            meta["fork_fallback"] = fb
                else:
                    print(
                        "pr_diff: could not parse owner/repo from meta.pr_url",
                        flush=True,
                    )
            else:
                print(
                    "pr_diff: fork_fallback.branch is placeholder and GITCODE_TOKEN not set; "
                    "cannot auto-fetch branch info from API.",
                    flush=True,
                )
        if br and "REPLACE" not in br.upper():
            ru = fb.get("remote_url")
            if not ru:
                raise SystemExit(
                    "fork_fallback.branch is set but fork_fallback.remote_url is missing in meta.json."
                )
            print(
                "pr_head: no matching ref on remote (GitCode often lacks pull/*/head). "
                "Using fork_fallback.branch …",
                flush=True,
            )
            apply_fetch_fork_branch(
                git_dir,
                {
                    "remote_name": fb.get("remote_name", "contributor"),
                    "remote_url": ru,
                    "remote_branch": br,
                    "local_branch": local_branch,
                },
            )
            return
        raise SystemExit(
            "Could not fetch PR head: this host has no pull/*/head ref. "
            "Set fork_fallback.branch in meta.json to the PR source branch name "
            "(see the PR page on GitCode), or replace the pr_head entry with "
            'a "fork_branch" fetch (see docs/meta-json.md).'
        )
    elif t == "fork_branch":
        apply_fetch_fork_branch(git_dir, item)
    elif t == "comment":
        pass
    else:
        raise SystemExit(f"Unknown fetch type: {t!r} in {item}")


def find_best_merge_base(git_dir: str, base_ref: str, head_ref: str) -> str:
    """Find the best common ancestor for diffing, preferring --fork-point when multiple exist."""
    # First try fork-point (more intelligent merge base for rebased branches)
    fp = subprocess.run(
        ["git", "merge-base", "--fork-point", base_ref, head_ref],
        cwd=git_dir, capture_output=True, text=True,
    )
    if fp.returncode == 0 and fp.stdout.strip():
        commit = fp.stdout.strip()
        print(f"+ git merge-base --fork-point {base_ref} {head_ref} = {commit[:8]}", flush=True)
        return commit

    # Fall back to default merge-base and check if multiple bases exist
    all_bases = subprocess.run(
        ["git", "merge-base", "--all", base_ref, head_ref],
        cwd=git_dir, capture_output=True, text=True,
    )
    if all_bases.returncode != 0 or not all_bases.stdout.strip():
        # Should not happen, but fall back to base_ref
        return base_ref

    bases = [b.strip() for b in all_bases.stdout.strip().splitlines() if b.strip()]
    if len(bases) <= 1:
        return bases[0] if bases else base_ref

    # Multiple merge bases: pick the one closest to head_ref (fewest commits between it and head)
    # This tends to be the most recent/common ancestor after rebase
    best_base, best_distance = None, float("inf")
    for base in bases:
        count = subprocess.run(
            ["git", "rev-list", "--ancestry-path", "--count", f"{base}..{head_ref}"],
            cwd=git_dir, capture_output=True, text=True,
        )
        if count.returncode == 0:
            try:
                dist = int(count.stdout.strip())
                if dist < best_distance:
                    best_distance = dist
                    best_base = base
            except ValueError:
                pass

    if best_base:
        print(
            f"  multiple merge bases detected, using closest to head: {best_base[:8]}",
            flush=True,
        )
        return best_base
    return bases[0]


def write_diff(git_dir: str, base_ref: str, head_ref: str, excludes: list[str], out_path: str) -> None:
    # Use two-dot diff (..) instead of three-dot (...) to avoid issues with
    # patch files containing nested diffs (which cause corrupted output with ...).
    # Two-dot shows direct differences, which is appropriate for PR review.
    pair = f"{base_ref}..{head_ref}"
    cmd = ["git", "diff", "--no-ext-diff", pair]
    if excludes:
        cmd += ["--", "."] + [f":(exclude){ex}" for ex in excludes]
    print("+ " + " ".join(cmd), flush=True)
    with open(out_path, "w", encoding="utf-8", errors="replace") as f:
        subprocess.run(cmd, cwd=git_dir, check=True, stdout=f, text=True)


def main() -> None:
    if len(sys.argv) != 4:
        print("Usage: pr_diff.py <meta.json> <git_dir> <out.patch>", file=sys.stderr)
        sys.exit(2)
    meta_path, git_dir, out_patch = sys.argv[1], sys.argv[2], sys.argv[3]
    with open(meta_path, encoding="utf-8") as fp:
        meta = json.load(fp)
    upstream = meta["upstream_git"]
    d = meta["diff"]
    base_ref = d["base_ref"]
    head_ref = d["head_ref"]
    excludes = list(d.get("exclude_paths") or [])

    clone_if_needed(git_dir, upstream)

    for item in d.get("fetch") or []:
        if isinstance(item, dict) and item.get("type") != "comment":
            apply_fetch(git_dir, item, meta)

    write_diff(git_dir, base_ref, head_ref, excludes, out_patch)
    st = os.stat(out_patch)
    print(f"Wrote {out_patch} ({st.st_size} bytes)", flush=True)


if __name__ == "__main__":
    main()
