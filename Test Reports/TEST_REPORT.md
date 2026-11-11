# CYBER WORKSPACE — Test Report (v1.0.0-rc.1)

**Date:** 2026-11-11
**Environment (automated):** Linux x86_64 sandbox, Python 3.12.16,
PySide6 6.12.0 (offscreen platform), psutil 7.2.2, websockets 16.0,
cryptography 44.0.3. No Windows desktop session and no Android SDK were
available in the delivery environment — that boundary is explicit below.

**Result: 45 / 45 automated tests pass** (16.55 s wall time, full suite).

### Re-verification (same day, fresh sandbox session)

The delivery sandbox was recycled between sessions, so the suite was run
again to confirm the tree as packaged still passes:

- Dependencies re-installed strictly from `Source/Windows/requirements.txt`
  (PySide6 6.12.0, psutil 7.2.2, websockets 16.0, cryptography 44.0.3).
- **Result: 44 passed, 1 skipped, 0 failed** — the skip is
  `tests/test_smoke_offscreen.py`, which imports `PySide6.QtWidgets`;
  that import links against the system library `libEGL.so.1`, and the
  fresh session provides no GL system libraries and no root access to
  install them (PySide6 itself bundles no `libEGL.so.1`, verified via
  `ldd`). This is an environmental limitation of the Linux sandbox, not
  a code change — the same test passed in the original session above.
  On Windows this dependency does not exist (PySide6 ships its own
  OpenGL backend), so the skip will not occur on the target platform.
- All engine, state-machine, timer, persistence, isolation, recovery and
  TLS remote-protocol tests are unaffected and green in both runs.

## Acceptance results

| Spec test | Status | Evidence / measurement |
| --- | --- | --- |
| A — multiple tasks | **PASS (automated)** | 6 live script processes RUNNING simultaneously; `test_a_six_tasks_run_simultaneously`; capacity default 12 |
| B — isolation: error | **PASS (automated)** | failing task → ERROR with "exit code 3"; 3 siblings stay RUNNING; `test_b_error_isolation` |
| C — isolation: approval | **PASS (automated)** | WAITING_FOR_USER + notification + stdin decision; approve→COMPLETED(exit 0), deny→ERROR(exit 4); siblings untouched |
| D — isolation: network | **PASS (automated)** | self-reported NETWORK_WAITING with reason, recovery → COMPLETED; siblings untouched |
| E — timer accuracy | **PASS (automated)** | active/waiting/error separation; **unknown never merged into active** (`test_unknown_never_merges_into_active`); freeze on COMPLETED; persistence roundtrip equality; orphan recovery uses cutoff; automation stall → UNKNOWN then UNRESPONSIVE |
| F — minimization | **PARTIAL** | engine/UI independence proven by design (§ARCHITECTURE threading) + offscreen smoke; **tray behaviour needs a real Windows desktop session** |
| G — power management | **PARTIAL (logic PASS)** | keep-awake evaluates selected RUNNING tasks only; WAITING/PAUSED excluded; restore-on-exit logic tested; actual `SetThreadExecutionState` effect needs Windows hardware |
| H — recovery | **PASS (automated)** | clean shutdown + crash paths; timers survive without double counting; surviving child process re-adopted (pid preserved, monitoring-only) |
| I — remote pairing | **PASS (automated, Python stand-in)** | real TLS + WSS: welcome/fingerprint, pre-auth rejection, single-use code, token auth, duplicate-session CONFLICT, bogus credential rejection, remote pause reaches engine + audit; **the Android APK itself was not compiled/run here** |
| J — resource use | **PASS (measured)** | 10 concurrent tasks: **avg engine tick 0.30 ms, p95 1.48 ms** on the sandbox CPU; 10/10 tasks running. Numbers are machine-specific — re-run `test_j_engine_tick_overhead_10_tasks` on target hardware and record |

## What was executed vs what was not

**Executed in the delivery environment**
- Full engine/state-machine/timer/persistence behaviour (script, terminal,
  external adapters; browser adapter import-guarded).
- Process supervision of real child processes (spawn, output markers,
  approval round-trip via stdin, pause via psutil suspend, exit-code
  evidence, re-attach).
- Remote protocol end-to-end over real TLS sockets (server + test client).
- Qt dashboard (main window, cards, panels, dialogs) in Qt offscreen mode.
- Android-side logic mirrored in self-contained JVM test design; Kotlin
  sources written against the pinned stack but **not compiled**.

**Not executable in the delivery environment (requires target machines)**
- Windows installer build (PyInstaller + Inno Setup) — scripted, unrun.
- Android APK build (Gradle + SDK 34) — scripted, unrun.
- Real tray icon interaction, DPI scaling, Win32 power API effect, WebView
  rendering performance — manual checklist in TESTING.md.

## Honesty guardrails verified by tests

(Both runs — the original 45/45 and the re-verification 44+1skip —
cover the guardrails below; only the offscreen Qt smoke test is
environment-dependent.)

- `test_close_is_never_completed` — closing reports UNKNOWN, never COMPLETED.
- `test_unknown_never_merges_into_active` — unverifiable time is never
  counted as productive work.
- `test_metrics_unavailable_is_none_not_fabricated` — unmeasurable ⇒ None/n-a.
- `test_power_manager_off_windows_reports_unsupported` — no fake keep-awake.
- `test_command_action_is_closed_set` — injection attempts rejected at the
  protocol boundary.

## Sign-off statement

Nothing in this report claims target-platform behaviour that has not been
observed. Features marked PARTIAL have their logic tested and their
platform-specific effect listed for on-target verification. This release is
labelled **1.0.0-rc.1 (release candidate)** precisely because of that
boundary — it is not silently branded "production-ready".

### Final integration pass (2026-11-11, icon integration)

The delivery sandbox was recycled again before the final phase; the approved
single-root tree was restored from the surviving source tree (file-for-file
content, same code) and the following integration changes were made:

- **App icon** (user-supplied crown image) wired on all three surfaces:
  `cyber_workspace.ico` embedded into the EXE via the PyInstaller spec,
  `SetupIconFile` in the Inno Setup script, `app.setWindowIcon()` loading the
  bundled PNG at runtime, and a full Android `mipmap-*` raster set
  (launcher / round / adaptive foreground) replacing the placeholder vector.
- `Source/Windows/run_app.py` fixed (imported the non-existent
  `cyber_workspace.ui.app`; now imports `cyber_workspace.app`).
- CI workflows re-pointed at the new layout and de-broken (removed the
  `--timeout` flag that required the absent `pytest-timeout` plugin; aligned
  Gradle version with `gradle-wrapper.properties`).

Because these edits touched Python sources and packaging configuration, the
suite was run **once** after the changes (not a repeated test cycle):

- **Result: 44 passed, 1 skipped, 0 failed** — identical to the
  re-verification above (`test_smoke_offscreen.py` skips for the same
  environmental reason: no `libEGL.so.1` in the sandbox). No regression
  introduced by the icon integration or reference repairs.
