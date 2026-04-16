#!/usr/bin/env python3
"""POST review markdown as a GitCode PR comment (API v5)."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def resolve_default_review_md(results_pr_dir: Path) -> Path | None:
    """Prefer review.md (often symlink to latest); else newest review-*.md by mtime."""
    direct = results_pr_dir / "review.md"
    if direct.is_file():
        return direct
    candidates = sorted(
        results_pr_dir.glob("review-*.md"),
        key=lambda p: p.stat().st_mtime,
    )
    return candidates[-1] if candidates else None


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def parse_pr_from_meta(meta: dict[str, Any]) -> tuple[str, str, int]:
    url = str(meta.get("pr_url") or "")
    m = re.search(
        r"https?://[^/]+/([^/]+)/([^/]+)/pull/(\d+)",
        url,
        re.I,
    )
    if m:
        return m.group(1), m.group(2), int(m.group(3))
    gc = meta.get("gitcode") or {}
    owner = gc.get("owner")
    repo = gc.get("repo")
    num = meta.get("pr_number")
    if owner and repo and num is not None:
        return str(owner), str(repo), int(num)
    sys.exit(
        "Cannot determine owner/repo/PR number: set pr_url (gitcode.com/.../pull/N) "
        "or gitcode.owner + gitcode.repo + pr_number in meta.json."
    )


def default_banner() -> str:
    return (
        "🤖 **本评论由本地 [Gemini CLI](https://github.com/google-gemini/gemini-cli) "
        "审查生成**（`code-review` 工作流）\n\n---\n\n"
    )


def main() -> None:
    ap = argparse.ArgumentParser(
        description=(
            "Post PR review markdown to GitCode as a comment. "
            "Without --review: uses results/pr-<id>/review.md if present, else the newest "
            "review-*.md by modification time."
        ),
    )
    ap.add_argument(
        "pr_folder_id",
        nargs="?",
        type=int,
        default=None,
        metavar="PR_ID",
        help="Folder id under workspace/inputs/ and results/ (e.g. 449)",
    )
    ap.add_argument("--meta", type=Path, help="Path to workspace/inputs/pr-*/meta.json")
    ap.add_argument(
        "--review",
        type=Path,
        help="Explicit review .md path (default: auto-select latest as described in --help)",
    )
    ap.add_argument(
        "--pr-id",
        type=int,
        default=None,
        dest="pr_id_flag",
        help="Same as positional PR_ID (default paths under workspace/inputs/ and results/)",
    )
    ap.add_argument("--dry-run", action="store_true", help="Print URL and size only, do not POST")
    ap.add_argument("--no-banner", action="store_true", help="Do not prepend automated banner")
    args = ap.parse_args()

    root = repo_root()
    pr_id = args.pr_folder_id or args.pr_id_flag or 449
    meta_path = args.meta or root / "workspace" / "inputs" / f"pr-{pr_id}" / "meta.json"
    results_pr = root / "results" / f"pr-{pr_id}"
    if args.review is not None:
        review_path = args.review
    else:
        resolved = resolve_default_review_md(results_pr)
        review_path = resolved or (results_pr / "review.md")

    if not meta_path.is_file():
        if args.meta is not None:
            sys.exit(f"Missing meta: {meta_path}")
        print(f"Bootstrapping {meta_path} …", file=sys.stderr)
        subprocess.run(
            [sys.executable, str(root / "scripts/lib/bootstrap_meta.py"), str(pr_id)],
            check=True,
        )
    if not meta_path.is_file():
        sys.exit(f"Missing meta: {meta_path}")
    if not review_path.is_file():
        sys.exit(f"Missing review: {review_path}")

    print(f"Review file: {review_path.resolve()}", file=sys.stderr)

    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)

    owner, repo, number = parse_pr_from_meta(meta)
    gc = meta.get("gitcode") or {}
    base = str(gc.get("api_base_url") or os.environ.get("GITCODE_API_BASE_URL") or "https://api.gitcode.com")
    base = base.rstrip("/")

    body_text = review_path.read_text(encoding="utf-8")
    if not args.no_banner:
        body_text = default_banner() + body_text

    token = (
        os.environ.get("GITCODE_TOKEN")
        or os.environ.get("GITCODE_PRIVATE_TOKEN")
        or os.environ.get("GITEA_TOKEN")
    )
    if not token and not args.dry_run:
        sys.exit(
            "Set GITCODE_TOKEN (or GITCODE_PRIVATE_TOKEN) to a GitCode personal access token "
            "with permission to comment on PRs. Create it under GitCode → Settings → Access tokens."
        )

    url = f"{base}/api/v5/repos/{owner}/{repo}/pulls/{number}/comments"
    payload = json.dumps({"body": body_text}, ensure_ascii=False).encode("utf-8")

    print(f"Owner={owner} repo={repo} PR=#{number}", file=sys.stderr)
    print(f"POST {url}", file=sys.stderr)
    print(f"Body size: {len(payload)} bytes", file=sys.stderr)

    if args.dry_run:
        return

    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    req.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            print(resp.status, file=sys.stderr)
            if raw:
                try:
                    data = json.loads(raw)
                    print(json.dumps(data, ensure_ascii=False, indent=2)[:4000])
                except json.JSONDecodeError:
                    print(raw[:4000])
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code}: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
