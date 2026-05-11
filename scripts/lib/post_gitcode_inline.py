#!/usr/bin/env python3
"""Post findings as line-specific or general comments to GitCode PR via API v5."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# Import from same lib
sys.path.insert(0, str(Path(__file__).parent))
from parse_section_e import parse_review_md, SectionEFinding
from diff_position import parse_diff, find_position


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def parse_pr_from_meta(meta: dict[str, Any]) -> tuple[str, str, int]:
    url = str(meta.get("pr_url") or "")
    m = re.search(
        r"https?://[^/]+/([^/]+)/([^/]+)/(?:pull|merge_requests)/(\d+)",
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
    raise SystemExit(
        "Cannot determine owner/repo/PR number: set pr_url (gitcode.com/.../pull/N) "
        "or gitcode.owner + gitcode.repo + pr_number in meta.json."
    )


def load_fingerprints(results_dir: Path) -> set[str]:
    """Load existing fingerprints to avoid double-posting."""
    fp_file = results_dir / ".inline-fingerprints.json"
    if fp_file.is_file():
        try:
            return set(json.loads(fp_file.read_text()))
        except (json.JSONDecodeError, OSError):
            pass
    return set()


def save_fingerprints(results_dir: Path, fps: set[str]) -> None:
    """Save fingerprints to avoid re-posting."""
    fp_file = results_dir / ".inline-fingerprints.json"
    try:
        fp_file.write_text(json.dumps(list(fps), ensure_ascii=False))
    except OSError as e:
        print(f"Warning: Could not save fingerprints: {e}", file=sys.stderr)


def post_comment(
    owner: str,
    repo: str,
    pr_number: int,
    body: str,
    path: str | None,
    position: int | None,
    token: str,
    base_url: str,
    side: str = "RIGHT",
) -> dict[str, Any] | None:
    """Post a comment to GitCode PR.

    If path and position are provided, posts as line-specific comment.
    Otherwise posts as general comment.
    """
    base = base_url.rstrip("/")
    if path and position is not None:
        url = f"{base}/api/v5/repos/{owner}/{repo}/pulls/{pr_number}/comments"
        payload = {
            "body": body,
            "path": path,
            "position": position,
            "side": side,
        }
    else:
        url = f"{base}/api/v5/repos/{owner}/{repo}/pulls/{pr_number}/comments"
        payload = {"body": body}

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    req.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if raw:
                return json.loads(raw)
            return {}
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code}: {err[:500]}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error posting comment: {e}", file=sys.stderr)
        return None


def format_inline_body(finding: SectionEFinding) -> str:
    """Format a Section E finding as an inline comment body."""
    priority_labels = {
        "P0": "🔴 P0",
        "P1": "🟠 P1",
        "P2": "🟡 P2",
        "P3": "⚪ P3",
    }
    badge = priority_labels.get(finding.priority, finding.priority)
    return f"**[E-{finding.index[2:]}] {badge} {finding.title}**\n\n{finding.body}"


def determine_side(finding: SectionEFinding, diff: dict) -> str:
    """Determine which side to comment on based on the diff context.

    If the relevant line is a deletion (in the old code), use LEFT side.
    Otherwise use RIGHT side.
    """
    result = find_position(diff, finding.file_path, finding.line, prefer_side="RIGHT")
    if result and result.new_line is None and result.old_line is not None:
        return "LEFT"
    return "RIGHT"


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Post Section E findings as line-specific or general comments to GitCode PR.",
    )
    ap.add_argument("pr_folder_id", nargs="?", type=int, default=None, help="PR folder id (e.g. 956)")
    ap.add_argument("--meta", type=Path, help="Path to meta.json")
    ap.add_argument("--review", type=Path, help="Path to review.md")
    ap.add_argument("--diff", type=Path, help="Path to diff.patch")
    ap.add_argument("--dry-run", action="store_true", help="Print comments without posting")
    ap.add_argument("--fallback-only", action="store_true", help="Skip inline, post all as general comments")
    ap.add_argument("--no-banner", action="store_true", help="Skip automated banner")
    args = ap.parse_args()

    root = repo_root()

    # Resolve PR id
    pr_id = args.pr_folder_id
    if pr_id is None and args.meta:
        # Extract from meta path
        m = re.search(r"pr-(\d+)", str(args.meta))
        if m:
            pr_id = int(m.group(1))

    if pr_id is None:
        print("Error: Could not determine PR id. Provide it as positional arg or via --meta.", file=sys.stderr)
        sys.exit(1)

    # Resolve paths
    meta_path = args.meta or root / "workspace" / "inputs" / f"pr-{pr_id}" / "meta.json"
    results_dir = root / "results" / f"pr-{pr_id}"
    review_path = args.review or results_dir / "review.md"
    diff_path = args.diff or root / "workspace" / f"pr-{pr_id}" / "diff.patch"

    # Bootstrap meta if needed
    if not meta_path.is_file():
        print(f"Bootstrapping {meta_path} ...", file=sys.stderr)
        import subprocess
        subprocess.run(
            [sys.executable, str(root / "scripts/lib/bootstrap_meta.py"), str(pr_id)],
            check=True,
        )

    # Load meta
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)

    owner, repo, number = parse_pr_from_meta(meta)
    gc = meta.get("gitcode") or {}
    base_url = str(gc.get("api_base_url") or os.environ.get("GITCODE_API_BASE_URL") or "https://api.gitcode.com")

    # Token
    token = os.environ.get("GITCODE_TOKEN") or os.environ.get("GITCODE_PRIVATE_TOKEN") or os.environ.get("GITEA_TOKEN") or ""
    if not token and not args.dry_run:
        print("Error: GITCODE_TOKEN not set. Set GITCODE_TOKEN or use --dry-run.", file=sys.stderr)
        sys.exit(1)

    # Load existing fingerprints
    existing_fps = load_fingerprints(results_dir) if not args.dry_run else set()
    new_fps: set[str] = set()

    # Parse findings
    findings = parse_review_md(review_path)
    if not findings:
        print("No Section E findings found in review.md", file=sys.stderr)
        sys.exit(0)

    print(f"Found {len(findings)} findings in {review_path}", file=sys.stderr)

    # Parse diff for position mapping
    diff_text = diff_path.read_text() if diff_path.is_file() else ""
    diff = parse_diff(diff_text) if diff_text else {}

    # Post each finding
    posted = 0
    skipped = 0
    fallback = 0

    for finding in findings:
        fingerprint = finding.fingerprint

        # Check if already posted
        if fingerprint in existing_fps:
            print(f"  [E-{finding.index[2:]}] Skipping (already posted)", file=sys.stderr)
            skipped += 1
            continue

        # Format body
        body = format_inline_body(finding)

        if args.fallback_only:
            # Post as general comment
            if args.dry_run:
                print(f"  [E-{finding.index[2:]}] Would post as general comment:", file=sys.stderr)
                print(f"    {body[:100]}...", file=sys.stderr)
            else:
                result = post_comment(owner, repo, number, body, None, None, token, base_url)
                if result:
                    posted += 1
                    new_fps.add(fingerprint)
                    print(f"  [E-{finding.index[2:]}] → general comment (posted)", file=sys.stderr)
                else:
                    print(f"  [E-{finding.index[2:]}] → general comment (failed)", file=sys.stderr)
            continue

        # Try inline comment
        side = determine_side(finding, diff)
        pos_result = find_position(diff, finding.file_path, finding.line, prefer_side=side)

        if pos_result:
            if args.dry_run:
                print(f"  [E-{finding.index[2:]}] Would post inline: {pos_result.path}:{pos_result.position} (side={side})", file=sys.stderr)
                print(f"    {body[:100]}...", file=sys.stderr)
                new_fps.add(fingerprint)
                posted += 1
            else:
                result = post_comment(
                    owner, repo, number, body,
                    pos_result.path, pos_result.position,
                    token, base_url, side=side,
                )
                if result:
                    posted += 1
                    new_fps.add(fingerprint)
                    print(f"  [E-{finding.index[2:]}] → inline {pos_result.path}:{pos_result.position} (posted)", file=sys.stderr)
                else:
                    # Fallback to general
                    result = post_comment(owner, repo, number, body, None, None, token, base_url)
                    if result:
                        fallback += 1
                        new_fps.add(fingerprint)
                        print(f"  [E-{finding.index[2:]}] → general (inline failed, fallback posted)", file=sys.stderr)
                    else:
                        print(f"  [E-{finding.index[2:]}] → FAILED", file=sys.stderr)
        else:
            # Fallback to general comment
            if args.dry_run:
                print(f"  [E-{finding.index[2:]}] Would post as general (position not found)", file=sys.stderr)
                print(f"    {body[:100]}...", file=sys.stderr)
                new_fps.add(fingerprint)
                posted += 1
            else:
                result = post_comment(owner, repo, number, body, None, None, token, base_url)
                if result:
                    fallback += 1
                    new_fps.add(fingerprint)
                    print(f"  [E-{finding.index[2:]}] → general (position not found)", file=sys.stderr)
                else:
                    print(f"  [E-{finding.index[2:]}] → FAILED", file=sys.stderr)

    # Save fingerprints
    if not args.dry_run and new_fps:
        all_fps = existing_fps | new_fps
        save_fingerprints(results_dir, all_fps)

    print(f"\nSummary: posted={posted}, skipped={skipped}, fallback={fallback}", file=sys.stderr)

    if args.dry_run:
        print("\nDry run - no actual comments posted.", file=sys.stderr)


if __name__ == "__main__":
    main()
