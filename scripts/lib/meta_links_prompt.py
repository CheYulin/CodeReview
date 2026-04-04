#!/usr/bin/env python3
"""Emit a Markdown 'Traceability' section from workspace/inputs meta.json for gemini -p."""
from __future__ import annotations

import json
import sys
from typing import Any


def _fmt_item(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        u = item.get("url") or item.get("link") or ""
        t = item.get("title") or item.get("label") or item.get("id") or ""
        if t and u:
            return f"{t}: {u}"
        return u or t or json.dumps(item, ensure_ascii=False)
    return str(item)


def build_traceability_block(meta: dict[str, Any]) -> str:
    lines = [
        "## Traceability (from meta.json for this run)",
        "",
        "This block is **authoritative** for PR / Issue / RFC links. Map review findings to these items when relevant.",
        "",
    ]
    pr_url = (meta.get("pr_url") or "").strip()
    pn = meta.get("pr_number")
    if pr_url:
        lines.append(f"- **Pull request**: {pr_url}")
    elif pn is not None:
        lines.append(f"- **Pull request**: #{pn}")

    related = meta.get("related") or {}
    desc = (related.get("description") or "").strip()
    if desc:
        lines.append(f"- **Scope / intent**: {desc}")

    issues: list[Any] = list(related.get("issues") or [])
    legacy = meta.get("issues")
    if isinstance(legacy, dict):
        for k, v in legacy.items():
            if v and isinstance(v, str):
                issues.append({"label": k, "url": v})
    elif isinstance(legacy, list):
        issues.extend(legacy)

    lines.append("- **Related issues**:")
    if issues:
        for item in issues:
            lines.append(f"  - {_fmt_item(item)}")
    else:
        lines.append(
            "  - *None listed — add `related.issues` (URLs or objects with title/url) "
            "or legacy `issues` {{name: url}} in meta.json.*"
        )

    rfcs: list[Any] = list(related.get("rfcs") or [])
    lines.append("- **RFCs / design documents**:")
    if rfcs:
        for item in rfcs:
            lines.append(f"  - {_fmt_item(item)}")
    else:
        lines.append("  - *None listed — add `related.rfcs` if this PR tracks design docs.*")

    closes = related.get("closes")
    if closes:
        if isinstance(closes, list):
            closes_s = ", ".join(str(x) for x in closes)
        else:
            closes_s = str(closes)
        lines.append(f"- **Expected to close / address (tracking)**: {closes_s}")

    lines.extend(
        [
            "",
            "In **Executive summary** and **§A 功能与需求**, tie conclusions to the issues/RFCs above when the diff supports it; "
            "cite issue/RFC identifiers or URLs.",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: meta_links_prompt.py <path/to/meta.json>", file=sys.stderr)
        sys.exit(2)
    path = sys.argv[1]
    with open(path, encoding="utf-8") as f:
        meta = json.load(f)
    print(build_traceability_block(meta))


if __name__ == "__main__":
    main()
