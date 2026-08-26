"""Behaviour tests for the Task Scheduler helper.

`[VERIFIED]` 2026-08-26 the operator had no 08:00 brief: `/var/log/syslog` showed cron logging
every hour to 00:00 and then nothing from 01:00 to 08:00, because the host slept and WSL was
suspended with it. A Windows task runs above WSL and starts it, which is the fix.

The thing worth testing is **path translation**, because the registration command needs the
project path twice in two different forms and a task with one wrong form registers cleanly and
then fails every run, silently.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.schedule_windows import build_command, main, to_windows_path


@pytest.mark.parametrize(
    ("wsl_path", "expected"),
    [
        (
            "/mnt/c/DSC/Career/Projects/SportWire",
            "C:\\DSC\\Career\\Projects\\SportWire",
        ),
        ("/mnt/d/tools/SportWire", "D:\\tools\\SportWire"),
        (
            "/mnt/c/Users/someone/My Projects/SportWire",
            "C:\\Users\\someone\\My Projects\\SportWire",
        ),
    ],
)
def test_a_wsl_path_becomes_its_windows_form(wsl_path: str, expected: str) -> None:
    """Both forms have to be right, and only one of them is the one you are looking at."""
    assert to_windows_path(Path(wsl_path)) == expected


def test_a_path_outside_the_windows_drives_is_refused(tmp_path: Path) -> None:
    """`[INFERRED]` A project inside the WSL filesystem has no Windows path at all.

    Guessing one would produce exactly the silently-broken task this script exists to prevent,
    so it raises and says to use cron instead.
    """
    with pytest.raises(ValueError, match="not on a mounted Windows drive"):
        to_windows_path(Path("/home/youssef/SportWire"))


def test_the_repetition_is_explicitly_endless() -> None:
    """`[VERIFIED]` 2026-08-26, inspected through PowerShell: omitting `-RepetitionDuration`
    leaves `Duration` empty with `StopAtDurationEnd: True`, and `[UNKNOWN]` whether Windows
    reads that as "forever" or "stop at the default".

    A scheduler that quietly stops repeating after a day is the failure this is meant to fix,
    so the endless duration is stated rather than defaulted.
    """
    command = build_command(Path("/mnt/c/SportWire"), interval_hours=8)

    assert "[TimeSpan]::MaxValue" in command


def test_a_missed_window_is_caught_up_rather_than_skipped() -> None:
    """`-StartWhenAvailable` is the whole point of choosing Task Scheduler.

    `[VERIFIED]` Cron's behaviour on 2026-08-26 was to skip the 08:00 run entirely once the
    machine had slept through it. A task that only fires on the exact minute would do the same,
    so the setting that runs it late is what makes this different rather than merely elsewhere.
    """
    command = build_command(Path("/mnt/c/SportWire"), interval_hours=8)

    assert "-StartWhenAvailable" in command


def test_the_interval_reaches_both_the_trigger_and_the_description() -> None:
    """A description that disagrees with the trigger is how a schedule gets misremembered."""
    command = build_command(Path("/mnt/c/SportWire"), interval_hours=6)

    assert "New-TimeSpan -Hours 6" in command
    assert "every 6 hours" in command


def test_the_command_carries_both_path_forms() -> None:
    """The WSL form does the work; the Windows form is there to check it against."""
    command = build_command(Path("/mnt/c/DSC/SportWire"), interval_hours=8)

    assert "/mnt/c/DSC/SportWire" in command
    assert "C:\\DSC\\SportWire" in command


def test_the_generated_schedule_follows_the_configured_interval(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`[INFERRED]` Two places holding the cadence is how a schedule and a brief come to
    disagree: the task fires every 12 hours while the brief is still sized for 8.

    The generator has no interval of its own; it reads the one the pipeline uses.

    ~~Asserted on the exit code.~~ **That asserted nothing**: a mutation hardcoding 8 back
    into the generator left this green, because printing the wrong command still exits 0. The
    emitted text is the only thing that matters here.
    """
    monkeypatch.setenv("POLL_INTERVAL_HOURS", "24")

    assert main(["--task-name", "T"]) == 0

    printed = capsys.readouterr().out
    assert "New-TimeSpan -Hours 24" in printed
    assert "every 24 hours" in printed
    assert "Hours 8)" not in printed


def test_an_interval_outside_the_offered_set_is_refused(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The generator enforces the same bounded set the settings do.

    `[INFERRED]` Otherwise it would happily register a task on a cadence the pipeline itself
    refuses to start with, which fails at 3am rather than at the moment of the mistake.
    """
    with pytest.raises(SystemExit):
        main(["--interval-hours", "5"])

    assert "must be one of" in capsys.readouterr().err
