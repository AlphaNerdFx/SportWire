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

Add one line, replacing the path with your own. Every 8 hours, on the hour:

```cron
0 */8 * * * cd "/path/to/SportWire" && ./.venv/bin/python main.py >> /tmp/sportwire.log 2>&1
```

- `0 */8 * * *` — minute 0, every 8th hour (00:00, 08:00, 16:00)
- **Use the venv's Python directly.** `cron` has almost no `PATH`; a bare `python` will
  usually not be found, and if it is found it will be the system one without your dependencies.
- `>> /tmp/sportwire.log 2>&1` — cron mails output by default, which usually goes nowhere.
  Redirect it or you will have no idea why a brief did not arrive.

Check it registered:

```bash
crontab -l
```

### The WSL caveat

`[Likely]` On Windows, WSL's `cron` only runs while a WSL instance is alive. Close every WSL
terminal and the daemon may stop with it, so briefs stop without any error. Starting the
service is not enough to survive a reboot:

```bash
sudo service cron start
```

If SportWire must run unattended on Windows, prefer Option B.

---

## Option B — Windows Task Scheduler

Survives reboots and runs with no terminal open. Preferred for a Windows host.

Create the task from an **Administrator** PowerShell, replacing the path:

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
