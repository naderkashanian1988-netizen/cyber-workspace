# CYBER WORKSPACE — Architecture

## 1. Principles

1. **Independent task lifecycle** — every task is a self-contained object
   (process/execution context + state machine + timer + logs + metrics). The
   engine isolates errors per-task: every adapter exception is caught inside
   that task's poll/intent handling only (`TaskEngine.tick` wraps each task
   separately; see `core/engine.py` and `test_engine_isolation.py`).
2. **Single writer** — task state changes ONLY inside the engine. The UI, the
   remote server and adapter reader threads never mutate state; they enqueue
   intents/commands that tick() applies in order. This removes race classes
   entirely.
3. **Honest telemetry** — every number on screen comes from psutil, OS
   counters, process exit codes or adapter evidence. Unmeasurable ⇒ `n/a`
   or UNKNOWN. CPU usage alone is never treated as proof of productive work.

## 2. Module map (Windows host)

```
┌──────────────────────────── app.py (entry) ────────────────────────────┐
│  QApplication · single-instance lock · settings · remote bootstrap      │
└──────────┬──────────────────────────────────────────────┬──────────────┘
           │                                              │
┌──────────▼───────────────┐                  ┌───────────▼─────────────┐
│ core/  (Qt-free)         │                  │ ui/  (PySide6)          │
│  engine.TaskEngine       │   EventBus       │  main_window (timers)   │
│   · tick(): poll →       │◄──────────────►  │  task cards + panels    │
│     intents → watchdog → │  per-subscriber  │  tray (QSystemTrayIcon) │
│     metrics → commands   │  queues          │  dialogs                │
│  state.py (8 states)     │                  │  rain_widget (optional) │
│  timers.TriTimer         │                  └─────────────────────────┘
│  task.Task / TaskConfig  │
└───────┬──────────┬───────┘
        │          │
┌───────▼───┐ ┌────▼──────────────┐   ┌──────────────────────────────┐
│ adapters/ │ │ persistence/      │   │ remote/ (daemon thread)      │
│ script    │ │ Database (WAL)    │   │  TLS + websockets.serve      │
│ terminal  │ │ repos: tasks,     │   │  pairing (1-use code)        │
│ external  │ │  segments, events,│   │  token auth (SHA-256 hash,   │
│ browser   │ │  notifications,   │   │   constant-time compare)     │
│ (guarded) │ │  devices, audit   │   │  commands → engine queue     │
└─────┬─────┘ └───────────────────┘   └──────────────┬───────────────┘
      │ subprocess.Popen / psutil                     │ protocol v1
      ▼                                               ▼
 OS processes (independent)                    Android over WSS/TLS
```

## 3. Threading model

| Thread | Owns | Talks to engine via |
| --- | --- | --- |
| Qt main | engine.tick() timer (1 s), UI timers, tray | direct (same thread) |
| adapter readers (per task) | stdout/stderr pumps | `task.emit()` → intent deque (lock-guarded) |
| RemoteServer (asyncio loop) | WSS sessions | inbound: `engine.submit_command()`; outbound: own EventBus queue |
| power thread | SetThreadExecutionState hold loop (ES_CONTINUOUS is per-thread) | commands from engine |

Crash-safety: an adapter reader thread dying cannot kill a task (engine
polls process liveness independently via `poll()`), and a task's reader never
touches another task.

## 4. Timer design (TEST E)

Wall-clock UTC segments persisted at every transition
(`timer_segments(start_utc, end_utc, kind)`). Exactly one open segment per
task; switching buckets = close+open in one call, so no gaps/overlaps.
Monotonic clock is used ONLY for the live in-flight display.

Bucket selection per state:
- `RUNNING` + adapter `verified_when_alive` (script) → **active**
- `RUNNING` + `verified_on_heartbeat` (automation) → active while heartbeat
  fresh; older → **unknown**; beyond timeout+grace → state UNRESPONSIVE
- `RUNNING` + `activity_window` (browser) → active within window, else unknown
- `RUNNING` + `unverifiable` (external GUI app) → **unknown** (honest)
- `WAITING_FOR_USER` / `NETWORK_WAITING` → waiting · `ERROR`/`UNRESPONSIVE` →
  error · `PAUSED` → paused · `UNKNOWN` → unknown · `COMPLETED` → frozen

Recovery: on startup, orphan segments (end_utc NULL) are closed at the task's
persisted `last_seen_utc` cutoff (`recover_orphans`), so a crash never
stretches or double-counts time (`test_orphan_recovery_uses_cutoff`,
`test_h_recovery_persists_tasks_and_timers`).

## 5. Why QtWebEngine (not WebView2)

The master spec allowed choosing one. WebView2 requires a per-machine OS
runtime installation step and a Windows-only loader; QtWebEngine ships inside
the PySide6 wheel, integrates into the Qt lifecycle, and exposes page events
(load started/finished, console messages) that map directly onto the adapter
interface — enabling honest NETWORK_WAITING on load failure and approval
requests via `window.cwApproval()`. It is an optional dependency: when absent,
the browser task type is disabled with an explanation and all other task types
keep working.

## 6. Data flow of one task (script example)

```
user "Add task" → engine.add_task → SQLite tasks row
  → ScriptAdapter.start (Popen argv list, pipes)
  → reader threads: lines → intents (log/activity/progress/markers)
  → tick(): poll() detects exit → intent 'exit'
  → _handle_exit: exit code 0 → COMPLETED (evidence) / non-zero → ERROR
  → TriTimer freezes; totals persisted; notification + bus events
  → UI card refresh; remote server forwards task_event to Android
```

## 7. Isolation proof obligations (mapped to tests)

| Guarantee | Test |
| --- | --- |
| 6+ tasks run concurrently | `test_a_six_tasks_run_simultaneously` |
| error in one does not stop others | `test_b_error_isolation` |
| approval wait does not stop others | `test_c_approval_isolation`, `test_c_deny_isolation` |
| network wait does not stop others | `test_d_network_waiting_isolation` |
| engine survives adapter exceptions | per-task try/except in `tick()` |
| close ≠ completed | `test_close_is_never_completed` |
