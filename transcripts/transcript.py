#!/usr/bin/env python3
"""Turn a Claude Code session log (`.jsonl`) into a readable Markdown
transcript: the user's messages, Claude's replies, and one line per
tool call (its description).  Tool output and thinking are left out.

Usage: `python3 transcript.py SESSION.jsonl OUT.md`; the title is
`OUT`'s name (e.g. `2026-11-20_10-33_scraftcam`).
"""

import json
import os
import re
import sys
from typing import Any

REMINDER: re.Pattern[str] = re.compile(
    r"<system-reminder>.*?</system-reminder>", re.DOTALL
)


def user_text(content: Any) -> str:
    """Return the user's own words from a message's content."""
    texts: list[str] = []
    if isinstance(content, str):
        texts.append(content)
    else:
        for block in content:
            if block.get("type") == "text":
                texts.append(block["text"])
    return REMINDER.sub("", "\n".join(texts)).strip()


def main() -> None:
    """Read the log and write the transcript."""
    source: str = sys.argv[1]
    target: str = sys.argv[2]
    title: str = os.path.splitext(os.path.basename(target))[0]
    lines: list[str] = [f"# Transcript: {title}", ""]
    with open(source, encoding="utf-8") as log:
        for raw in log:
            record: dict[str, Any] = json.loads(raw)
            kind: str = record.get("type", "")
            message: Any = record.get("message")
            if not isinstance(message, dict):
                continue
            content: Any = message.get("content")
            if kind == "user":
                text: str = user_text(content)
                if text:
                    lines += ["## User", "", text, ""]
            elif kind == "assistant" and isinstance(content, list):
                for block in content:
                    if block.get("type") == "text" and block["text"].strip():
                        lines += ["## Claude", "", block["text"].strip(), ""]
                    elif block.get("type") == "tool_use":
                        about: str = block.get("input", {}).get(
                            "description", ""
                        )
                        lines += [f"*({block['name']}: {about})*", ""]
    with open(target, "w", encoding="utf-8") as out:
        out.write("\n".join(lines))


if __name__ == "__main__":
    main()
