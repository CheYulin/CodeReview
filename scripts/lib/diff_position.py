#!/usr/bin/env python3
"""Parse unified diff and map path:line to GitCode position.

GitCode/GitHub uses a 1-based position integer that counts lines from the
start of the diff file to the target "+" line, inclusive.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass
class DiffHunk:
    """A single hunk in a file diff."""
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str]  # All lines including hunk header
    # Line number tracking per line
    old_lines: list[int | None]  # Old file line numbers (None for + lines)
    new_lines: list[int | None]  # New file line numbers (None for - lines)


@dataclass
class FileDiff:
    """All hunks for a single file in a diff."""
    old_path: str
    new_path: str
    hunks: list[DiffHunk]


@dataclass
class PositionResult:
    """Result of finding a position in the diff."""
    path: str        # The path string for the API (e.g. "src/foo.cpp")
    position: int    # 1-based line count from diff start
    old_line: int | None  # Original line number (for context)
    new_line: int | None  # New line number
    exact_match: bool  # True if we found an exact line match


# Regex to match hunk headers: @@ -old_start,old_count +new_start,new_count @@
HUNK_RE = re.compile(
    r"^@@ -(?P<old_start>\d+)(?:,(?P<old_count>\d+))? \+(?P<new_start>\d+)(?:,(?P<new_count>\d+))? @@"
)


def parse_diff(diff_text: str) -> dict[str, FileDiff]:
    """Parse unified diff into a dict: new_path -> FileDiff."""
    files: dict[str, FileDiff] = {}
    current_old_path: str | None = None
    current_new_path: str | None = None
    current_hunks: list[DiffHunk] = []
    current_hunk_lines: list[str] = []
    current_old_lines: list[int | None] = []
    current_new_lines: list[int | None] = []
    old_line: int | None = None
    new_line: int | None = None
    in_hunk = False

    for raw_line in diff_text.splitlines():
        # Check for hunk header
        hunk_match = HUNK_RE.match(raw_line)
        if hunk_match:
            # Save previous hunk if exists
            if current_hunk_lines and old_line is not None and new_line is not None:
                current_hunks.append(DiffHunk(
                    old_start=old_line,
                    old_count=0,
                    new_start=new_line,
                    new_count=0,
                    lines=current_hunk_lines,
                    old_lines=current_old_lines,
                    new_lines=current_new_lines,
                ))

            old_start = int(hunk_match.group("old_start"))
            new_start = int(hunk_match.group("new_start"))
            old_line = old_start
            new_line = new_start
            current_hunk_lines = [raw_line]
            current_old_lines = []
            current_new_lines = []
            in_hunk = True
            continue

        # Check for file header (diff --git a/path b/path)
        if raw_line.startswith("diff --git"):
            # Save any pending hunk from previous file first
            if current_hunk_lines and old_line is not None and new_line is not None:
                current_hunks.append(DiffHunk(
                    old_start=old_line,
                    old_count=0,
                    new_start=new_line,
                    new_count=0,
                    lines=current_hunk_lines,
                    old_lines=current_old_lines,
                    new_lines=current_new_lines,
                ))
            # Save previous file if exists
            if current_new_path is not None and current_hunks:
                files[current_new_path] = FileDiff(
                    old_path=current_old_path or "",
                    new_path=current_new_path,
                    hunks=current_hunks,
                )
                current_hunks = []

            # Parse new path from diff --git a/path b/path
            parts = raw_line.split(" b/", 1)
            if len(parts) == 2:
                current_old_path = parts[1]
                current_new_path = parts[1]
            current_hunk_lines = []
            current_old_lines = []
            current_new_lines = []
            in_hunk = False
            continue

        if raw_line.startswith("--- ") or raw_line.startswith("+++ "):
            # Parse old/new paths from ---/+++ lines
            if raw_line.startswith("--- "):
                path = raw_line[4:]
                if path.startswith("a/"):
                    path = path[2:]
                current_old_path = path
            elif raw_line.startswith("+++ "):
                path = raw_line[4:]
                if path.startswith("b/"):
                    path = path[2:]
                current_new_path = path
            continue

        # Regular diff line - add to current hunk
        if in_hunk and current_new_path is not None:
            current_hunk_lines.append(raw_line)
            current_old_lines.append(None)
            current_new_lines.append(None)

            # Track line numbers
            if old_line is not None and new_line is not None:
                prefix = raw_line[:1] if raw_line else ""
                if prefix == "+":
                    current_new_lines[-1] = new_line
                    new_line += 1
                elif prefix == "-":
                    current_old_lines[-1] = old_line
                    old_line += 1
                elif prefix == " ":
                    current_old_lines[-1] = old_line
                    current_new_lines[-1] = new_line
                    old_line += 1
                    new_line += 1

    # Save last file
    if current_new_path is not None:
        # First save any pending hunk
        if current_hunk_lines and old_line is not None and new_line is not None:
            current_hunks.append(DiffHunk(
                old_start=old_line,
                old_count=0,
                new_start=new_line,
                new_count=0,
                lines=current_hunk_lines,
                old_lines=current_old_lines,
                new_lines=current_new_lines,
            ))
        if current_hunks:
            files[current_new_path] = FileDiff(
                old_path=current_old_path or "",
                new_path=current_new_path,
                hunks=current_hunks,
            )

    return files


def find_position(
    diff: dict[str, FileDiff],
    review_path: str,
    approx_line: int,
    max_distance: int = 10,
    prefer_side: str = "RIGHT",
) -> PositionResult | None:
    """Map a path:line from review to a GitCode position.

    Args:
        diff: Parsed diff from parse_diff()
        review_path: File path from review (e.g. "src/foo.cpp")
        approx_line: Approximate line number from review
        max_distance: Max distance to consider a valid match
        prefer_side: "RIGHT" for new code (+ lines), "LEFT" for old code (- lines)

    Returns:
        PositionResult with path and 1-based position, or None if not found
    """
    # Normalize path - try direct match and with common prefixes
    file_diff: FileDiff | None = None

    # Try exact match first
    if review_path in diff:
        file_diff = diff[review_path]
    else:
        # Try stripping common prefixes
        for key in diff:
            if key.endswith(review_path) or review_path.endswith(key):
                file_diff = diff[key]
                break

    if file_diff is None:
        return None

    # Find the closest line to approx_line
    position = 0
    best_match: tuple[int, int, int | None, int | None] | None = None  # (distance, position, old_line, new_line)

    for hunk in file_diff.hunks:
        for line_idx, line in enumerate(hunk.lines):
            position += 1

            old_l = hunk.old_lines[line_idx] if line_idx < len(hunk.old_lines) else None
            new_l = hunk.new_lines[line_idx] if line_idx < len(hunk.new_lines) else None

            # For RIGHT side, look at + lines (new file)
            # For LEFT side, look at - lines (old file)
            target_line: int | None = None
            if prefer_side == "RIGHT" and line.startswith("+") and new_l is not None:
                target_line = new_l
            elif prefer_side == "LEFT" and line.startswith("-") and old_l is not None:
                target_line = old_l
            elif not line.startswith("+") and not line.startswith("-"):
                # Context lines - check both old and new
                if new_l is not None:
                    target_line = new_l
                elif old_l is not None:
                    target_line = old_l

            if target_line is not None:
                distance = abs(target_line - approx_line)
                if best_match is None or distance < best_match[0]:
                    best_match = (distance, position, old_l, new_l)

    if best_match is None:
        return None

    distance, pos, old_l, new_l = best_match
    if distance > max_distance:
        return None

    return PositionResult(
        path=file_diff.new_path,
        position=pos,
        old_line=old_l,
        new_line=new_l,
        exact_match=(distance == 0),
    )


if __name__ == "__main__":
    import sys
    from pathlib import Path

    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <diff.patch>", file=sys.stderr)
        sys.exit(1)

    diff_text = Path(sys.argv[1]).read_text()
    diff = parse_diff(diff_text)

    print(f"Parsed {len(diff)} files from diff")
    for path, file_diff in list(diff.items())[:5]:
        print(f"  {path}: {len(file_diff.hunks)} hunks")

    # Test finding a position
    if diff:
        first_path = list(diff.keys())[0]
        result = find_position(diff, first_path, 10)
        if result:
            print(f"\nTest find_position({first_path}, 10):")
            print(f"  position={result.position}, new_line={result.new_line}, exact={result.exact_match}")
