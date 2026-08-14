"""Fails when a documentation link points at something that does not exist.

`[VERIFIED]` 2026-08-14 this is not hypothetical. The GitHub wiki linked to
`docs/decisions/ADR-012-summarisation-off-by-default.md` for eight days. The file had been
renamed to `ADR-012-summarisation.md` when the decision reversed on 2026-08-10, and the wiki
also still *described* the superseded decision. Nothing noticed, because nothing looked.

The wiki's own Home page says "This wiki navigates. It does not duplicate" — written
specifically so it could not drift. It drifted anyway. `[INFERRED]` A rule that depends on
remembering is not a mechanism; this is the mechanism.

Two kinds of link are checked:

  - **Repo markdown** — every `[text](relative/path)` must resolve to a real file.
  - **Wiki markdown** — every `.../blob/main/<path>` must resolve to a real file in the repo,
    and every wiki-internal `[text](Page-Name)` must resolve to a real wiki page.

The wiki lives in a separate git repository (`<repo>.wiki.git`), so it is only checked when a
clone is available. Pass `--wiki <dir>`, or set `SPORTWIRE_WIKI`. Without it the wiki portion
is skipped loudly rather than silently — a check that quietly does nothing is worse than no
check, because it reports success.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# `[text](target)` — deliberately only real markdown links. Bare paths in prose and inside
# backticks are not links, and treating them as such produces false failures on template
# placeholders like `docs/decisions/ADR-NNN-<slug>.md`.
_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")

# A wiki link into the repository's source tree.
_BLOB = re.compile(r"^https://github\.com/[^/]+/[^/]+/blob/[^/]+/(.+)$")

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


def check_wiki_links(wiki: Path, root: Path) -> list[str]:
    """Wiki links must resolve, both into the repo and to other wiki pages."""
    failures: list[str] = []
    pages = {path.stem for path in wiki.glob("*.md")}

    for markdown in sorted(wiki.glob("*.md")):
        for target in _LINK.findall(markdown.read_text(encoding="utf-8")):
            blob = _BLOB.match(target)
            if blob:
                path = blob.group(1).split("#", 1)[0]
                if not (root / path).exists():
                    failures.append(
                        f"wiki/{markdown.name}: repo file does not exist -> {path}"
                    )
                continue

            if _is_external(target):
                continue

            # A wiki-internal page reference, e.g. [Architecture](Architecture).
            page = target.split("#", 1)[0].rstrip("/")
            if page and page not in pages and not (wiki / page).exists():
                failures.append(f"wiki/{markdown.name}: no such wiki page -> {page}")

    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wiki",
        default=os.environ.get("SPORTWIRE_WIKI", ""),
        help="path to a clone of <repo>.wiki.git; skipped when absent",
    )
    args = parser.parse_args(argv)

    failures = check_repo_links(REPO_ROOT)
    checked = "repository markdown"

    wiki = Path(args.wiki).expanduser() if args.wiki else None
    if wiki and wiki.is_dir():
        failures += check_wiki_links(wiki, REPO_ROOT)
        checked += " and wiki"
    else:
        # Loud, not silent. A skipped check that prints nothing reports success it has not
        # earned -- the same shape as the legacy suite passing in 3.32s without asserting.
        print(
            "SKIPPED the wiki: no clone available. Pass --wiki <dir> or set SPORTWIRE_WIKI.\n"
            "         git clone https://github.com/AlphaNerdFx/SportWire.wiki.git",
            file=sys.stderr,
        )

    if failures:
        print(f"\nBroken documentation links ({len(failures)}):\n", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    print(f"All documentation links resolve ({checked}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
