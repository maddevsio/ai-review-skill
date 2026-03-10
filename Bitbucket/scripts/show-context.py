#!/usr/bin/env python3
"""
Extracts code context from an annotated diff for a specific file and line range.
Outputs a markdown diff code block for display during comment moderation.

Usage:
    python3 show-context.py <pr_number> <file_path> <line>
    python3 show-context.py <pr_number> <file_path> <start_line> <end_line>

Reads from /tmp/pr-diff-<pr_number>.txt (written by annotate-diff.py).
Prints a markdown ```diff block to stdout, or nothing if context is unavailable.
"""

import re
import sys

CONTEXT_LINES = 3


def find_file_section(lines: list[str], file_path: str) -> list[str]:
    """
    Extracts lines belonging to the given file's section from the annotated diff.
    Matches against 'diff --git' headers and '+++ b/<path>' lines.
    """
    section_start = -1
    section_end = len(lines)

    # Try to match by full path first, then by basename
    def matches(line: str) -> bool:
        return file_path in line

    for i, line in enumerate(lines):
        if line.startswith("diff --git"):
            if section_start >= 0:
                # We were already in a section; this is the next file — stop
                section_end = i
                break
            if matches(line):
                section_start = i
        elif line.startswith("+++ b/") and section_start < 0:
            # Fallback: match on +++ b/ header
            if file_path in line or file_path.split("/")[-1] in line:
                # Walk back to find the diff --git line
                for j in range(i, -1, -1):
                    if lines[j].startswith("diff --git"):
                        section_start = j
                        break

    if section_start < 0:
        return []

    return lines[section_start:section_end]


def extract_context(
    section: list[str], start_line: int, end_line: int
) -> list[str]:
    """
    Returns annotated diff lines whose new-file line number falls within
    [start_line - CONTEXT_LINES, end_line + CONTEXT_LINES].
    Removed lines (-) adjacent to included lines are kept.
    Gaps between included lines are replaced with '   ...' separators.
    """
    lo = max(1, start_line - CONTEXT_LINES)
    hi = end_line + CONTEXT_LINES

    line_pattern = re.compile(r"^\s*(\d+) \u2502")  # matches "  44 │"
    removed_pattern = re.compile(r"^\s+ \u2502 -")   # matches "     │ -"

    # Tag each line with its new-file line number (None for removed/header lines)
    tagged: list[tuple[int | None, str]] = []
    for line in section:
        m = line_pattern.match(line)
        if m:
            tagged.append((int(m.group(1)), line))
        else:
            tagged.append((None, line))

    # Find indices of numbered lines in range
    in_range: set[int] = set()
    for i, (ln, _) in enumerate(tagged):
        if ln is not None and lo <= ln <= hi:
            in_range.add(i)
            # Pull in adjacent removed lines before this index
            if i > 0 and tagged[i - 1][0] is None and removed_pattern.match(tagged[i - 1][1]):
                in_range.add(i - 1)
            # Pull in adjacent removed lines after this index
            if i + 1 < len(tagged) and tagged[i + 1][0] is None and removed_pattern.match(tagged[i + 1][1]):
                in_range.add(i + 1)

    if not in_range:
        return []

    sorted_indices = sorted(in_range)
    result: list[str] = []
    prev: int | None = None

    for idx in sorted_indices:
        if prev is not None and idx > prev + 1:
            result.append("   ...")
        result.append(tagged[idx][1])
        prev = idx

    return result


def main() -> None:
    if len(sys.argv) < 4:
        print(
            f"Usage: {sys.argv[0]} <pr_number> <file_path> <line> [end_line]",
            file=sys.stderr,
        )
        sys.exit(1)

    pr_number = sys.argv[1]
    file_path = sys.argv[2]
    start_line = int(sys.argv[3])
    end_line = int(sys.argv[4]) if len(sys.argv) > 4 else start_line

    diff_path = f"/tmp/pr-diff-{pr_number}.txt"
    try:
        with open(diff_path) as f:
            content = f.read()
    except FileNotFoundError:
        # Degrade gracefully — moderation continues without context
        sys.exit(0)

    lines = content.splitlines()
    section = find_file_section(lines, file_path)
    if not section:
        sys.exit(0)

    context_lines = extract_context(section, start_line, end_line)
    if not context_lines:
        sys.exit(0)

    print("```diff")
    for line in context_lines:
        print(line)
    print("```")


if __name__ == "__main__":
    main()
