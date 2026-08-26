"""Emit the PowerShell that registers SportWire with Windows Task Scheduler.

**Why this exists rather than a copy-paste block in the documentation.** The command needs the
project path twice, in two different forms — `C:\\...` for Windows and `/mnt/c/...` for WSL —
and both must be right. `[INFERRED]` A hand-edited path that is wrong in one of the two forms
produces a task that registers cleanly and then fails every run, which is the worst shape of
error this project keeps meeting: silent, scheduled, and invisible until somebody notices no
brief arrived.

**Why Task Scheduler at all.** `[VERIFIED]` 2026-08-26: the operator had no 08:00 brief.
`/var/log/syslog` showed cron logging every hour up to 00:00 and then **nothing from 01:00 to
08:00**, including the system's own ten-minute jobs. The host slept, WSL was suspended with it,
and cron does not run a job it missed. A Windows task runs at the Windows level and starts WSL
itself, so it survives sleep and reboots.

**This prints; it does not register.** Registering needs Administrator and changes the machine,
so the operator runs the command themselves and sees exactly what it will do first.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Run directly (`python scripts/schedule_windows.py`), so the project root is not on the path.
# `[INFERRED]` The alternative is duplicating the interval choices here, and two places holding
# the same set is how they come to disagree.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import (
    DEFAULT_POLL_INTERVAL_HOURS,
    POLL_INTERVAL_CHOICES,
    Settings,
    SettingsError,
)

TASK_NAME = "SportWire"

# `/mnt/c/Users/...` -> `C:\Users\...`. WSL mounts each Windows drive under /mnt/<letter>.
_WSL_MOUNT = re.compile(r"^/mnt/([a-z])/(.*)$")


def to_windows_path(wsl_path: Path) -> str:
    """Translate a WSL path into the Windows form Task Scheduler needs.

    Raises rather than guessing when the project is not on a mounted Windows drive.
    `[INFERRED]` A project inside the WSL filesystem itself (`/home/...`) has no Windows path,
    and inventing one would produce exactly the silently-broken task this script exists to
    prevent.
    """
    match = _WSL_MOUNT.match(str(wsl_path))
    if not match:
        raise ValueError(
            f"{wsl_path} is not on a mounted Windows drive, so it has no Windows path. "
            "Task Scheduler cannot reach it; use cron instead, or move the project under "
            "/mnt/c."
        )
    drive, rest = match.groups()
    return f"{drive.upper()}:\\" + rest.replace("/", "\\")


def build_command(
    project: Path, interval_hours: int, task_name: str = TASK_NAME
) -> str:
    """The PowerShell that registers the task, with both path forms filled in.

    `-RepetitionDuration ([TimeSpan]::MaxValue)` is deliberate and not decoration.
    `[VERIFIED]` 2026-08-26, inspected via PowerShell: omitting it leaves `Duration` empty with
    `StopAtDurationEnd: True`, and `[UNKNOWN]` whether Windows reads that as "repeat forever"
    or "stop at the default". The explicit form produces `P99999999DT23H59M59S`, which removes
    the question. A scheduler that quietly stops repeating after a day is the failure this is
    supposed to fix.
    """
    windows_path = to_windows_path(project)
    return f"""# Run this in an **Administrator** PowerShell.
$action = New-ScheduledTaskAction -Execute "wsl.exe" `
    -Argument '-e bash -c "cd ''{project}'' && ./.venv/bin/python main.py"'
$trigger = New-ScheduledTaskTrigger -Once -At 12am `
    -RepetitionInterval (New-TimeSpan -Hours {interval_hours}) `
    -RepetitionDuration ([TimeSpan]::MaxValue)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
    -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries
Register-ScheduledTask -TaskName "{task_name}" -Action $action -Trigger $trigger `
    -Settings $settings -Description "SportWire NBA brief every {interval_hours} hours"

# Project (Windows form, for reference): {windows_path}

# Check it, and run it now rather than waiting {interval_hours} hours:
Get-ScheduledTask -TaskName "{task_name}"
Start-ScheduledTask -TaskName "{task_name}"
Get-ScheduledTaskInfo -TaskName "{task_name}"   # LastTaskResult 0 means success

# Remove it:
# Unregister-ScheduledTask -TaskName "{task_name}" -Confirm:$false"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--interval-hours",
        type=int,
        default=None,
        help=(
            "how often to deliver a brief. Defaults to POLL_INTERVAL_HOURS from your "
            "configuration, so the schedule and the brief's size cannot disagree"
        ),
    )
    parser.add_argument(
        "--task-name",
        default=TASK_NAME,
        help=f"Task Scheduler name (default: {TASK_NAME})",
    )
    args = parser.parse_args(argv)

    # Default to the configured interval rather than a second hardcoded 8. `[INFERRED]` Two
    # places holding the cadence is how a schedule and a brief quietly come to disagree: the
    # task would fire every 12 hours while the brief was still sized for 8.
    interval = args.interval_hours
    if interval is None:
        try:
            interval = Settings.from_env().poll_interval_hours
        except SettingsError:
            # Configuration may be incomplete on a machine that has not been set up yet, and
            # printing a scheduler command is exactly what you do *before* that is finished.
            interval = DEFAULT_POLL_INTERVAL_HOURS

    if interval not in POLL_INTERVAL_CHOICES:
        offered = ", ".join(str(choice) for choice in POLL_INTERVAL_CHOICES)
        parser.error(f"--interval-hours must be one of {offered}, got {interval}")

    project = Path(__file__).resolve().parent.parent
    try:
        print(build_command(project, interval, args.task_name))
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
