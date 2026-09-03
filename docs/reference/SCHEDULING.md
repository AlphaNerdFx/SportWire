# Running SportWire on a schedule

SportWire does **not** schedule itself. `main.py` runs once and exits; the operating system
decides when to run it.

That is deliberate. An in-process `while True: sleep(8h)` loop is a program that must survive
for months. One unhandled exception and briefs stop arriving — silently, because nothing is
watching it. It does not restart after a reboot, it does not survive a WSL shutdown, and
changing the schedule means killing and restarting the process. `cron` and Task Scheduler
already solve all of that, and cost one line of configuration instead of code to maintain.

> `[VERIFIED]` 2026-08-06 — a scheduled run starts in a **different working directory** from a
> manual one. SportWire locates `.env` and its database relative to the project itself, so
> both behave identically. If you fork this and add another file path, anchor it the same way
> (`config.settings.PROJECT_ROOT`), or scheduled runs will silently read the wrong thing.

---

## Option A — cron (Linux, macOS, WSL)

Portable, and the right choice if you are publishing or running on a server.

```bash
crontab -e
```

Add one line, replacing the path with your own. **On a laptop, use this form:**

```cron
*/30 * * * * cd "/path/to/SportWire" && ./.venv/bin/python main.py --if-due >> /tmp/sportwire.log 2>&1
```

- `*/30 * * * *` with `--if-due` — cron wakes the program every half hour and the program
  decides whether a brief is actually due, from when it last delivered one.
- `[VERIFIED]` 2026-08-27, and this is why the form changed. The old line was
  `0 */8 * * *`, minute 0 of every eighth hour, which fires **only if the machine happens to
  be awake at that exact minute**. On the operator's laptop it slept through both the 08:00
  and the 16:00 slot in a single day, so no brief arrived at all. Syslog shows cron silent
  from 03:28 to 10:55 and again from 15:25 to 16:25.
- `[INFERRED]` `--if-due` costs almost nothing on the wake-ups where nothing is due: it reads
  one row from the database and exits before contacting any source.
- On a machine that is always on, `0 */8 * * *` without `--if-due` is still fine and is one
  fewer moving part.
- **Use the venv's Python directly.** `cron` has almost no `PATH`; a bare `python` will
  usually not be found, and if it is found it will be the system one without your dependencies.
- `>> /tmp/sportwire.log 2>&1` — cron mails output by default, which usually goes nowhere.
  Redirect it or you will have no idea why a brief did not arrive.

Check it registered:

```bash
crontab -l
```

### The WSL caveat

~~`[Likely]` On Windows, WSL's `cron` only runs while a WSL instance is alive.~~
**`[VERIFIED]` 2026-08-26, and it is worse than "while a terminal is open": it stops while the
machine sleeps.**

The operator reported no 08:00 brief. From `/var/log/syslog`, cron logged between 3 and 7
entries every hour from 2026-08-25 14:00 through 2026-08-26 00:00, including the 00:00
SportWire run, and then **nothing at all for hours 01:00 to 08:00** — not even the system's own
ten-minute jobs. The laptop slept, WSL was suspended with it, and **cron does not run a job it
missed.** The brief did not fail; it never started, and nothing in the application log says so.

`[VERIFIED]` **Do not use `uptime` to check this.** It reported 8 hours 27 minutes of
continuous uptime across the exact window in which nothing ran, because WSL2 keeps counting
while the VM is paused. The gap in `/var/log/syslog` is the evidence. To check whether cron has
actually been alive:

```bash
grep -i CRON /var/log/syslog | awk '{print $1, $2, substr($3,1,2)":00"}' | uniq -c | tail
```

An hour with no entries is an hour in which no scheduled job could have run.

Starting the service is not enough to survive a reboot:

```bash
sudo service cron start
```

If SportWire must run unattended on Windows, prefer Option B.

---

## Option B — Windows Task Scheduler

Survives reboots and runs with no terminal open. Preferred for a Windows host.

**Generate the command instead of editing it by hand:**

```bash
python scripts/schedule_windows.py                    # every 8 hours, the default
python scripts/schedule_windows.py --interval-hours 6
```

`[INFERRED]` The path appears twice below in two different forms, and a task with one of them
wrong registers cleanly and then fails every run — silently, on a schedule, until somebody
notices no brief arrived. The script derives both from where it is, so there is nothing to
mistype. It **prints** the command rather than running it, because registering needs
Administrator and changes the machine.

Two things the generated command adds that the block below originally lacked:

- `[VERIFIED]` `-RepetitionDuration ([TimeSpan]::MaxValue)`. Without it, `Duration` is empty
  with `StopAtDurationEnd: True`, and `[UNKNOWN]` whether Windows reads that as "repeat
  forever" or "stop at the default". Stating it removes the question.
- `-StartWhenAvailable`, so a run missed while the machine was off happens late rather than
  not at all. That is the entire reason for choosing Task Scheduler over cron.

Or create it from an **Administrator** PowerShell by hand, replacing the path:

```powershell
$project = "C:\path\to\SportWire"
$action  = New-ScheduledTaskAction -Execute "wsl.exe" `
    -Argument "-e bash -c `"cd '/mnt/c/path/to/SportWire' && ./.venv/bin/python main.py`""
$trigger = New-ScheduledTaskTrigger -Once -At 12am `
    -RepetitionInterval (New-TimeSpan -Hours 8)
Register-ScheduledTask -TaskName "SportWire" -Action $action -Trigger $trigger `
    -Description "NBA brief to Telegram every 8 hours"
```

Note the path appears twice in two different forms: `C:\...` for Windows and `/mnt/c/...`
for WSL. Both must be correct.

Verify and test without waiting eight hours:

```powershell
Get-ScheduledTask -TaskName "SportWire"
Start-ScheduledTask -TaskName "SportWire"     # run it right now
Get-ScheduledTaskInfo -TaskName "SportWire"   # LastTaskResult 0 means success
```

Remove it:

```powershell
Unregister-ScheduledTask -TaskName "SportWire" -Confirm:$false
```

---

## Before you schedule anything

Run it manually once, exactly as the scheduler will — from a **different directory**, with an
absolute path:

```bash
cd /tmp && /path/to/SportWire/.venv/bin/python /path/to/SportWire/main.py --dry-run
```

If that prints a brief, the scheduled run will work. If it reports missing configuration,
the scheduler would have failed the same way, silently, three times a day.

## Letting something else deliver the brief

If an external tool should forward the brief somewhere SportWire does not support — another
chat app, a webhook, a file — use the stdout channel rather than `--dry-run`:

```bash
./.venv/bin/python main.py --channel stdout | your-relay-command
```

`--channel stdout` prints the brief **and records it as delivered**, exactly as Telegram does.
`--dry-run` prints and records nothing, so a relay built on it would re-send every story on
every run, forever. Messages are separated by a line containing `---`.

`[VERIFIED]` The difference, run twice each:

|                      | first run                        | second run                                |
| -------------------- | -------------------------------- | ----------------------------------------- |
| `--channel stdout` | 17 articles printed and recorded | nothing — "0 articles (17 already sent)" |
| `--dry-run`        | 17 articles printed              | the same 17 again                         |

> **On assistants that reach WhatsApp.** Tools such as OpenClaw can invoke SportWire and relay
> its output to WhatsApp. `[VERIFIED]` They generally do so through Baileys, an unofficial
> WhatsApp Web bridge that violates WhatsApp's terms and risks a permanent account ban.
> SportWire therefore ships **no** such integration and never will (ADR-013) — but nothing
> stops you running one yourself against this stdout channel. That is your account and your
> risk, and it stays outside this repository.

## Changing the interval

The cron expression or the Task Scheduler trigger is the **only** thing that sets the
cadence. `POLL_INTERVAL_HOURS` in `.env` is documentation of intent — nothing reads it to
decide when to run, because nothing is running between invocations to read it.

`[VERIFIED]` The summary window follows automatically: each run reports whatever survived
deduplication, which is everything new since the previous run. Change the schedule and the
window changes with it, with no other edit (PRD D1).
