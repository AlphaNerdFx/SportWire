"""Behaviour tests for the documentation link check.

`scripts/check_links.py` gates `make check`, so a bug in it silently stops guarding every
document in the project — the same failure shape as a test that asserts nothing.

`[VERIFIED]` It was written after a real incident: `ADR-012` was renamed on 2026-08-10 when
the summarisation decision reversed, and three documents kept linking to the old filename for
four days — `README.md`, `SECURITY.md`, and the wiki's Decisions page. All three also still
*described* the superseded decision. `test_catches_the_real_adr_012_regression` reproduces
exactly that shape.

Everything here builds throwaway trees under `tmp_path`; nothing reads the real repository, so
these tests cannot start passing for the wrong reason when the real docs change.

`[VERIFIED]` 2026-09-03 the wiki was retired into `docs/` and the four tests covering
`check_wiki_links` went with the function they tested. Deleting a test whose subject no
longer exists is not the same as weakening one, and leaving them would have meant a suite
asserting behaviour of code that is not there.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_links import check_repo_links

BLOB = "https://github.com/AlphaNerdFx/SportWire/blob/main"


def _write(root: Path, name: str, body: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


# --- repository links --------------------------------------------------------------------


def test_a_resolving_relative_link_passes(tmp_path: Path) -> None:
    _write(tmp_path, "docs/real.md", "content")
    _write(tmp_path, "README.md", "See [the doc](docs/real.md).")

    assert check_repo_links(tmp_path) == []


def test_a_broken_relative_link_fails(tmp_path: Path) -> None:
    """The whole point. A link to a file that does not exist must be reported."""
    _write(tmp_path, "README.md", "See [the doc](docs/missing.md).")

    failures = check_repo_links(tmp_path)

    assert len(failures) == 1
    assert "docs/missing.md" in failures[0]
    assert "README.md" in failures[0], (
        "the report must name the file containing the link"
    )


def test_relative_links_resolve_from_the_containing_file(tmp_path: Path) -> None:
    """A link in `docs/a.md` to `b.md` means `docs/b.md`, not `b.md` at the root."""
    _write(tmp_path, "docs/b.md", "content")
    _write(tmp_path, "docs/a.md", "See [b](b.md).")

    assert check_repo_links(tmp_path) == []


@pytest.mark.parametrize(
    "target",
    [
        "https://example.com/whatever",
        "http://example.com",
        "#a-heading-anchor",
        "mailto:someone@example.com",
    ],
)
def test_external_and_anchor_links_are_not_checked(target: str, tmp_path: Path) -> None:
    """Only links this repository can actually verify are in scope."""
    _write(tmp_path, "README.md", f"See [it]({target}).")

    assert check_repo_links(tmp_path) == []


def test_a_blob_link_into_this_repo_is_checked(tmp_path: Path) -> None:
    """An absolute GitHub link into our own tree rots on rename exactly like a relative one,
    so it is deliberately not treated as external."""
    _write(tmp_path, "README.md", f"See [the doc]({BLOB}/docs/missing.md).")

    failures = check_repo_links(tmp_path)

    assert len(failures) == 1
    assert "docs/missing.md" in failures[0]


def test_an_anchor_on_a_real_file_is_not_a_broken_link(tmp_path: Path) -> None:
    """`file.md#section` points at a real file; the fragment is not part of the path."""
    _write(tmp_path, "docs/real.md", "content")
    _write(tmp_path, "README.md", "See [it](docs/real.md#a-section).")

    assert check_repo_links(tmp_path) == []


def test_inline_code_is_not_treated_as_a_link(tmp_path: Path) -> None:
    """`[text](target)` only. `[VERIFIED]` Template placeholders like
    `docs/decisions/ADR-NNN-<slug>.md` appear in backticks throughout `CLAUDE.md`, and
    treating bare paths as links would fail on every one of them."""
    _write(
        tmp_path, "README.md", "Write it to `docs/decisions/ADR-NNN-<slug>.md` first."
    )

    assert check_repo_links(tmp_path) == []


def test_the_venv_is_not_scanned(tmp_path: Path) -> None:
    """Dependency documentation is not ours to keep correct, and scanning it is slow."""
    _write(tmp_path, ".venv/lib/some_package/README.md", "See [x](totally/missing.md).")

    assert check_repo_links(tmp_path) == []


def test_catches_the_real_adr_012_regression(tmp_path: Path) -> None:
    """`[VERIFIED]` 2026-08-14, reproducing the incident that prompted this script.

    `ADR-012-summarisation-off-by-default.md` was renamed to `ADR-012-summarisation.md` on
    2026-08-10. `README.md`, `SECURITY.md` and the wiki all kept the old link for four days.

    `[VERIFIED]` 2026-09-03 the wiki was retired into `docs/`, so its third of this case is now
    an ordinary repository file and is asserted as one. The incident is unchanged; only where
    the third document lives has changed.
    """
    repo = tmp_path / "repo"
    old = "docs/decisions/ADR-012-summarisation-off-by-default.md"

    _write(repo, "docs/decisions/ADR-012-summarisation.md", "the renamed file")
    _write(repo, "README.md", f"see [ADR-012]({old})")
    _write(repo, "SECURITY.md", f"see [ADR-012]({old})")
    _write(repo, "docs/decisions/README.md", f"see [012]({BLOB}/{old})")

    failures = check_repo_links(repo)

    assert len(failures) == 3, f"expected all three, got {failures}"
    assert all("ADR-012-summarisation-off-by-default" in f for f in failures)


def test_a_clean_tree_reports_nothing(tmp_path: Path) -> None:
    """The complement: a check that always fails is as useless as one that never does."""
    repo = tmp_path / "repo"
    _write(repo, "docs/real.md", "content")
    _write(repo, "docs/README.md", f"[doc]({BLOB}/docs/real.md) and [near](real.md).")

    assert check_repo_links(repo) == []
