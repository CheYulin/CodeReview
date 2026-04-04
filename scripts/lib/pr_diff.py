#!/usr/bin/env python3
"""Clone upstream if needed, run meta.json fetch steps, write git diff to patch file."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from typing import Any


def run(cmd: list[str], cwd: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=cwd, check=check, text=True)


def clone_if_needed(git_dir: str, upstream: str) -> None:
    """Ensure git_dir is a clone of upstream. Existing repos are only updated, never deleted."""
    git_internal = os.path.join(git_dir, ".git")
    if os.path.isdir(git_internal):
        print("+ git fetch origin  # existing clone, refresh refs only", flush=True)
        subprocess.run(["git", "fetch", "origin"], cwd=git_dir, check=False)
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
    # GitHub / Gitea / some hosts; GitLab-style MR refs; GitCode often has none of these.
    return [
        f"refs/pull/{pr}/head:{local_branch}",
        f"pull/{pr}/head:{local_branch}",
        f"refs/merge-requests/{pr}/head:{local_branch}",
        f"merge-requests/{pr}/head:{local_branch}",
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
    run(["git", "fetch", rn, f"{rb}:{lb}"], cwd=git_dir)


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


def write_diff(git_dir: str, base_ref: str, head_ref: str, excludes: list[str], out_path: str) -> None:
    triple = f"{base_ref}...{head_ref}"
    cmd = ["git", "diff", triple]
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
