#!/usr/bin/env python3
"""Merge CLI --issues / --rfcs into workspace/inputs meta.json (and sync pr_url)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def issue_base_url() -> str:
    host = os.environ.get("CODE_REVIEW_GITCODE_HOST", "gitcode.com")
    owner = os.environ.get("CODE_REVIEW_GITCODE_OWNER", "openeuler")
    repo = os.environ.get("CODE_REVIEW_GITCODE_REPO", "yuanrong-datasystem")
    return f"https://{host}/{owner}/{repo}/issues"


def pr_url(pr_id: int) -> str:
    host = os.environ.get("CODE_REVIEW_GITCODE_HOST", "gitcode.com")
    owner = os.environ.get("CODE_REVIEW_GITCODE_OWNER", "openeuler")
    repo = os.environ.get("CODE_REVIEW_GITCODE_REPO", "yuanrong-datasystem")
    return f"https://{host}/{owner}/{repo}/pull/{pr_id}"


def main() -> None:
    ap = argparse.ArgumentParser(description="Update meta.json with --issues / --rfcs from CLI.")
    ap.add_argument("--meta", type=Path, required=True, help="Path to meta.json")
    ap.add_argument("--pr", type=int, required=True, help="PR number (sync pr_url / pr_number)")
    ap.add_argument("--issues", type=str, default="", help="Comma-separated issue numbers, e.g. 234,233,235")
    ap.add_argument("--rfcs", type=str, default="", help="Pipe-separated RFC URLs, e.g. https://a|https://b")
    args = ap.parse_args()

    base = issue_base_url()
    with open(args.meta, encoding="utf-8") as f:
        meta = json.load(f)

    meta["pr_number"] = args.pr
    meta["pr_url"] = pr_url(args.pr)

    rel = meta.setdefault("related", {})
    if not isinstance(rel, dict):
        rel = {}
        meta["related"] = rel

    if args.issues.strip():
        nums: list[int] = []
        for part in args.issues.split(","):
            p = part.strip()
            if not p:
                continue
            try:
                nums.append(int(p))
            except ValueError:
                print(f"Ignoring non-integer issue token: {p!r}", file=sys.stderr)
        rel["issues"] = [f"{base}/{n}" for n in nums]
        rel["closes"] = nums
        meta.pop("issues", None)
    if args.rfcs.strip():
        urls = [u.strip() for u in args.rfcs.split("|") if u.strip()]
        rel["rfcs"] = urls

    with open(args.meta, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Updated {args.meta} (PR #{args.pr}, related issues/rfcs)", file=sys.stderr)


if __name__ == "__main__":
    main()
