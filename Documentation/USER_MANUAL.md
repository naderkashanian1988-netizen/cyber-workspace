# CYBER WORKSPACE — User Manual

**Version 1.0.0-rc.1 · Windows 10/11 x64 + Android companion**

## 1. The dashboard

Top bar: title, lightweight **digital rain** (disable in Settings), network
status LED, keep-awake ☕ indicator, and quick actions
(＋ Add task · ⚡ Power · 🔔 Notifications · 📶 Network · 📱 Devices ·
🔑 Pair · ⚙ Settings · Exit).

Left column: **task cards** — one independent card per task, drag to reorder
(order is saved). Right column: overview / network / power / notification
panels. Status bar shows recent engine messages.

## 2. Task cards

Each card shows: status LED + state chip, app/page, reason line (why the task
is in its state), **active · waiting · error** timers, CPU/RAM (n/a when not
measurable), last activity timestamp, last progress, and controls
(⏸ pause · ▶ resume · ⟳ restart · ☕ keep-awake · ✕ close).

Click a card for the detail view: all five timer buckets
(active/waiting/error/paused/unknown), pid, exit code, progress, logs, stdin
line input (script/terminal), and approval answering.

## 3. Timer honesty — what counts as "Active"

| Task type | Active time counts when… | Otherwise |
| --- | --- | --- |
| Script | the process is executing (its running IS the evidence) | — |
| Automation script (`require_heartbeat`) | it prints `@@CW:HEARTBEAT@@` recently | unknown; long silence → UNRESPONSIVE |
| Terminal | the shell is alive | — |
| External app | **never fabricated** — running GUI time is shown as Unknown | unknown |
| Browser tab | page events / your interaction within the activity window | unknown after ~90 s idle |

Waiting time accrues in WAITING_FOR_USER and NETWORK_WAITING. Error time in
ERROR / UNRESPONSIVE. Paused time is tracked separately. Unknown time is
shown separately and **never** merged into active. Timers survive restarts
and crashes without double counting.

## 4. Adding tasks

＋ Add task → choose type:
- **script** — interpreter (default: workspace Python) + script path + args +
  workdir; optional heartbeat mode. Exit code 0 → COMPLETED, non-zero →
  ERROR (evidence-based).
- **terminal** — PowerShell / cmd / pwsh / custom shell; typing goes to its
  stdin from the detail view.
- **external** — any EXE + args; the app keeps its own window (no fragile
  embedding); we supervise the process, not the window.
- **browser** — URL in a QtWebEngine tab (option hidden with an explanation
  if WebEngine is unavailable).

### Script marker protocol (optional, for script authors)
Print to stdout (flush!):
```
@@CW:PROGRESS@@ {"note": "step 3/10"}
@@CW:APPROVAL@@ {"question": "Deploy now?", "options": ["Yes","No"]}
@@CW:NETWAIT@@ {"reason": "upload endpoint unreachable"}
@@CW:NETOK@@
@@CW:HEARTBEAT@@
```
The workspace stops the active timer while waiting for your approval and
delivers the decision to the script's stdin as `approve <id>` / `deny <id>`.
Browser pages can request approval with
`console.log("CW_APPROVAL:" + JSON.stringify({question:"..."}))`.

## 5. Notifications

Every notification names the ONE task that needs you. Click **Open** (or the
toast) to open exactly that task — nothing else is disturbed. Approval
notifications carry Approve/Deny buttons; the task keeps its
WAITING_FOR_USER state until you decide.

## 6. Power & sleep (⚡ Power)

- **☕ Keep-awake** — enable per task (card ☕ button). While a selected task
  is RUNNING, the workspace uses `SetThreadExecutionState` to prevent system
  sleep. It is a temporary override; permanent power plans are never touched,
  and normal behaviour resumes when you disable it, the task stops, or the
  workspace exits.
- **Facts**: display-off does NOT stop tasks. **Sleep/hibernate WILL suspend
  task execution** — no exceptions, and this workspace never promises
  otherwise.
- Buttons open the real Windows pages: Power & Sleep, Screen Saver, Display;
  plus `powercfg /a` standby capabilities (read-only).

## 7. System tray

Minimize to tray keeps everything running (background work continues
independently). The tray shows running/waiting counts, opens the notification
center, restores the window, and exits **safely** (processes stopped, timers
closed, session saved).

## 8. Recovery after a crash

On the next launch the workspace restores all tasks and timers, tells you
what it could and could not recover (UNKNOWN with an explicit reason), and —
when a task's process actually survived the crash — re-attaches to it for
monitoring. A terminated external process cannot be restored to its exact
previous execution state; the workspace reports honestly instead of guessing.

## 9. Android companion

Pair once (see INSTALL.md). The phone mirrors every task card, tri-timers,
CPU/RAM, network status and notifications; you can pause/resume/restart/close
and answer approvals (control permission). **Windows execution always stays
on the Windows machine** — the phone is a secure monitor/controller, and
local Android tasks (URL monitors) are subject to Android's background
restrictions (suspended intervals are reported as Unknown, never as work).

## 10. Remote test client (no phone needed)

```bash
python Source/Shared/tools/remote_test_client.py pair --host 192.168.1.10 --port 47770 --code 482913
python Source/Shared/tools/remote_test_client.py watch --host 192.168.1.10 --port 47770 \
    --device-id <id> --token <token> --seconds 20
```

## 11. FAQ

**Q: My task's window closed — is it done?**
A: Only scripts with real exit-code semantics can be reported COMPLETED.
Everything else shows UNKNOWN with the reason — we never guess.

**Q: Why does a GUI app show Unknown instead of Active time?**
A: We cannot verify productive work inside an arbitrary GUI; fabricating
numbers is worse than honest Unknown.

**Q: Will tasks keep running when the PC sleeps?**
A: No. Keep-awake prevents sleep while you ask for it; sleep/hibernate
suspends execution regardless of any app.

**Q: Can I run more than 10 tasks?**
A: Yes — Settings → Max tasks (default 12). Scale subject to device
resources; TEST J measures per-tick overhead in the test report.
