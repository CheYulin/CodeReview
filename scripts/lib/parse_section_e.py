#!/usr/bin/env python3
"""Parse Section E findings from review.md."""
from __future__ import annotations

import re
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SectionEFinding:
    """A single Section E finding."""
    index: str      # "E-1"
    priority: str   # "P0"|"P1"|"P2"|"P3"
    dimension: str  # "功能"|"性能"|"缺陷"|"风格"
    file_path: str  # e.g. "src/foo.cpp"
    line: int       # line number from diff
    title: str      # title/heading after [E-N] [P#]
    body: str       # 问题 + 建议 formatted for comment
    fingerprint: str  # SHA1 for deduplication

    @classmethod
    def from_match(cls, index: str, priority: str, title_with_dim: str,
                   path: str, line: int, body_text: str) -> "SectionEFinding":
        # Parse dimension from title like "功能|缺陷" or "性能"
        parts = title_with_dim.split("|")
        dimension = parts[0].strip() if parts else ""

        # Format body as markdown
        body_lines = []
        if "问题：" in body_text:
            # Only include lines from 问题： onwards (skip code excerpt)
            in_problem = False
            for part in body_text.split("\n"):
                stripped = part.strip()
                if "问题：" in part:
                    in_problem = True
                    body_lines.append(f"**问题**: {stripped.split('问题：', 1)[1].strip()}")
                elif "建议：" in part:
                    body_lines.append(f"**建议**: {stripped.split('建议：', 1)[1].strip()}")
                elif in_problem and stripped:
                    # Continuation of 问题 or 建议 (wrapped lines)
                    body_lines.append(stripped)
        else:
            body_lines.append(body_text.strip())

        body = "\n\n".join(body_lines)

        # Generate fingerprint for deduplication
        fp_input = f"{index}|{path}|{line}|{priority}"
        fingerprint = hashlib.sha1(fp_input.encode("utf-8")).hexdigest()[:16]

        return cls(
            index=index,
            priority=priority,
            dimension=dimension,
            file_path=path,
            line=line,
            title=title_with_dim,
            body=body,
            fingerprint=fingerprint,
        )


# Regex to match Section E finding inside ```text block
# [E-N] [P#] 维度：xxx
# - 位置：path:line
# ... rest of body ...
FINDING_RE = re.compile(
    r"\[E-(\d+)\]\s*\[(P\d+)\]\s*维度：([^\n]+)\n"
    r"- 位置：`?([^:`]+):(\d+)`?\n"
    r"(.*?)"
    r"(?=\[E-\d+\]|$)",
    re.DOTALL,
)


def parse_review_md(review_path: Path) -> list[SectionEFinding]:
    """Extract all Section E findings from a review.md file."""
    text = review_path.read_text(encoding="utf-8", errors="replace")

    # Find Section E content - everything between "### E. 具体优化与重构" and the next ### or end
    section_e_match = re.search(
        r"### E\.\s*具体优化与重构.*?\n+```[a-z]*\n(.*?)```",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not section_e_match:
        return []

    section_e_content = section_e_match.group(1)

    findings: list[SectionEFinding] = []
    for match in FINDING_RE.finditer(section_e_content):
        index = match.group(1)
        priority = match.group(2)
        title_with_dim = match.group(3).strip()
        path = match.group(4).strip()
        line = int(match.group(5))
        body_text = match.group(6).strip()

        finding = SectionEFinding.from_match(
            index=f"E-{index}",
            priority=priority,
            title_with_dim=title_with_dim,
            path=path,
            line=line,
            body_text=body_text,
        )
        findings.append(finding)

    return findings


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <review.md>", file=sys.stderr)
        sys.exit(1)
    findings = parse_review_md(Path(sys.argv[1]))
    for f in findings:
        print(f"  [{f.index}] [{f.priority}] {f.title}")
        print(f"    位置: {f.file_path}:{f.line}")
        print(f"    fingerprint: {f.fingerprint}")
        print(f"    body: {f.body[:80]}...")
        print()
