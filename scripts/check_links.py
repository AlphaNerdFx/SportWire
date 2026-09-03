"""Fails when a documentation link points at something that does not exist.

`[VERIFIED]` 2026-08-14 this is not hypothetical. The GitHub wiki linked to
`docs/decisions/ADR-012-summarisation-off-by-default.md` for eight days. The file had been
renamed to `ADR-012-summarisation.md` when the decision reversed on 2026-08-10, and the wiki
also still *described* the superseded decision. Nothing noticed, because nothing looked.

The wiki's own Home page said "This wiki navigates. It does not duplicate" — written
specifically so it could not drift. It drifted anyway. `[INFERRED]` A rule that depends on
remembering is not a mechanism; this is the mechanism.

`[VERIFIED]` 2026-09-03 the wiki was retired and its pages moved into `docs/`, so the second
half of this checker went with it. It used to resolve `.../blob/main/<path>` links in a clone
of `<repo>.wiki.git` and needed `--wiki` or `SPORTWIRE_WIKI` to run at all, which meant the
common case was a check that skipped. What remains is the half that always ran: every
`[text](relative/path)` in the repository must resolve to a real file.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# An absolute link into this repository's own tree. `[VERIFIED]` 2026-09-03 this outlived the
# wiki half it was written for: repository markdown still writes the occasional full GitHub URL
# to its own files, and those rot on a rename exactly like a relative one.
_BLOB = re.compile(r"^https://github\.com/[^/]+/[^/]+/blob/[^/]+/(.+)$")

# `[text](target)` — deliberately only real markdown links. Bare paths in prose and inside
# backticks are not links, and treating them as such produces false failures on template
# placeholders like `docs/decisions/ADR-NNN-<slug>.md`.
_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")

# Directories with no documentation worth checking.
_SKIP_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
}


def _markdown_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.md")
        if not any(part in _SKIP_DIRS for part in path.parts)
    )


def _is_external(target: str) -> bool:
    """Anchors, mail and anything not on this repository's blob path are out of scope."""
    if target.startswith(("#", "mailto:")):
        return True
    # An http(s) link is external *unless* it points into this repository's own tree, in
    # which case it is exactly the kind of link that silently rots when a file is renamed.
    return target.startswith(("http://", "https://")) and not _BLOB.match(target)


def check_repo_links(root: Path) -> list[str]:
    """Every relative markdown link in the repository must resolve to a real file."""
    failures: list[str] = []

    for markdown in _markdown_files(root):
        for target in _LINK.findall(markdown.read_text(encoding="utf-8")):
            if _is_external(target):
                continue

            blob = _BLOB.match(target)
            path = blob.group(1) if blob else target.split("#", 1)[0]
            if not path:
                continue

            base = root if blob else markdown.parent
            if not (base / path).exists():
                rel = markdown.relative_to(root)
                failures.append(f"{rel}: link target does not exist -> {path}")

    return failures


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)

    failures = check_repo_links(REPO_ROOT)

    if failures:
        print(f"\nBroken documentation links ({len(failures)}):\n", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    print("All documentation links resolve.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
