# CYBER WORKSPACE — Testing

## Run everything (Windows host)

```powershell
cd Source\Windows
.\.venv\Scripts\python -m pytest tests\ -q        # 45 tests
```
On non-Windows machines the suite runs fully too — Windows-only calls are
platform-guarded and report "unsupported" honestly.

## Acceptance criteria → test mapping (master spec §18)

| Spec test | Automated test(s) | What proves readiness |
| --- | --- | --- |
| **A — multiple tasks** | `test_engine_isolation.py::test_a_six_tasks_run_simultaneously` | six live script processes RUNNING at once; capacity default 12 |
| **B — isolation (error)** | `::test_b_error_isolation` | failing task → ERROR("exit code 3"), 3 siblings keep RUNNING |
| **C — isolation (approval)** | `::test_c_approval_isolation`, `::test_c_deny_isolation` | WAITING_FOR_USER + notification + approve/deny via stdin; siblings untouched |
| **D — isolation (network)** | `::test_d_network_waiting_isolation` | self-reported NETWORK_WAITING → recovers → COMPLETED; siblings untouched |
| **E — timer accuracy** | `test_timers.py` (5 tests), `test_recovery.py::test_unresponsive_watchdog` | active/waiting/error separation; unknown never merged into active; freeze on COMPLETED; minimized-state irrelevant (bucket logic is state-driven) |
| **F — minimization** | `test_smoke_offscreen.py` (UI live while engine runs) + architecture §3 (tray only mirrors; engine independent) | on-target tray check still required |
| **G — power management** | `test_power.py` (3 tests) | keep-awake follows selected RUNNING tasks only; WAITING/PAUSED don't justify wake; API unsupported off-Windows reports honestly |
| **H — recovery** | `test_recovery.py::test_h_recovery_persists_tasks_and_timers`, `::test_h_recovery_adopts_surviving_process` | sessions + timer totals survive clean shutdown and crash; orphan segments closed at cutoff without double counting; surviving child adopted |
| **I — remote pairing** | `test_remote.py` (3 tests) | full pairing→auth→subscribe over real TLS; pre-auth command rejected; duplicate session CONFLICT; bogus token/device rejected; remote command reaches engine + audit log |
| **J — resource use** | `test_metrics.py::test_j_engine_tick_overhead_10_tasks` | measured (see TEST_REPORT.md), no fabricated claims |

Plus foundations: `test_state.py` (state machine law), `test_protocol.py`
(closed command set = injection boundary), `test_persistence.py` (hashed
tokens, schema, repos), `test_smoke_offscreen.py` (Qt dashboard end-to-end in
offscreen mode).

## Android unit tests
```bash
cd android && ./gradlew testDebugUnitTest
```
(ProtocolModelsTest · TriTimerTest · TlsPinningTest — self-contained JVM tests.)

## Manual on-target checklist (Windows + Android)

1. Launch → tray icon appears; minimize to tray → tasks keep running (F).
2. Open Power panel buttons → correct Windows pages (G).
3. Pair a real phone; approve a scripted approval request from the phone (I).
4. Kill a task's process via Task Manager → workspace reports UNKNOWN, never
   COMPLETED, siblings untouched.
5. Record TEST J numbers on your hardware and append to TEST_REPORT.md.
