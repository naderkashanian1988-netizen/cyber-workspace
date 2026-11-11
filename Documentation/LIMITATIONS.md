# CYBER WORKSPACE — Known Limitations

Read this before relying on the product. Everything here is a deliberate,
documented honesty decision — not a hidden defect.

## Platform truthfulness

1. **Windows execution stays on Windows.** The Android app monitors and
   controls the paired host; it does NOT keep Windows programs running on its
   own, and never claims to.
2. **Sleep/hibernate suspends task execution.** Keep-awake only prevents
   *system sleep* while selected tasks run; it cannot keep tasks running
   through sleep, hibernate or shutdown, and the product never promises it.
3. **Android background limits.** Local Android tasks run in a foreground
   service and are subject to Doze/App Standby; suspended intervals are
   reported as UNKNOWN, not silently counted as work.

## Measurement honesty

4. **Per-task network attribution is not implemented.** Reliable per-process
   byte counters on Windows need elevated ETW/packet-counter APIs we refuse
   to require. The Network Monitor shows real system-wide speeds + TCP
   connect latency; per-task network reads `n/a` unless an adapter
   self-reports.
5. **GUI app "active work" is unverifiable.** External applications accrue
   UNKNOWN time while running — never fabricated active time.
6. **Browser idle ≠ active.** Browser tabs count active time only within a
   ~90 s activity window; idle browsing is honest Unknown.
7. **Latency is TCP-connect**, not ICMP (raw sockets would need elevation).

## Lifecycle honesty

8. **Closed window ≠ completed.** Only script tasks with real exit-code
   semantics can be COMPLETED. External apps / terminals / browser tabs that
   disappear become UNKNOWN with an explicit reason.
9. **Re-attachment is monitoring-only.** After a crash, surviving child
   processes are adopted for supervision, but their original stdin/stdout
   pipes are gone: no stdin control, output resumes only for what the adapter
   can capture. Browser tabs cannot be re-adopted at all.
10. **Terminal/external `pause` is not implemented** (script tasks pause via
    `psutil.suspend()`). The card disables pause where unsupported.
11. **Restart = new run.** Timer totals are lifetime segments; restart does
    not reset them (documented in the detail view).

## Technical scope

12. **Browser tasks need QtWebEngine** (bundled). If unavailable, the browser
    type is disabled with an explanation; other task types are unaffected.
13. **Single-host, LAN scope.** The remote server is designed for LAN use
    behind a firewall; do not expose it to the internet without a VPN.
14. **Max 8 paired devices** (enforced); one session per device.
15. **Delivery environment boundary.** The sandbox that produced this tree is
    Linux: installer/APK compilation, real-desktop tray behaviour, Win32
    power API behaviour and WebView rendering require on-target verification
    (see TEST_REPORT.md's exact pass/partial/pending table).
16. **No automatic updates.** Updates are manual; the protocol version check
    protects against incompatible hosts/clients (VERSIONING.md).
17. **Logs grow unbounded** in `task_events`/`audit_log` (metrics are
    ring-buffered). Trim manually or wait for schema v2 rotation.

## Android build notes

18. The Gradle wrapper JAR is intentionally not committed — run
    `gradle wrapper` or open in Android Studio (README-ANDROID.md).
19. The Android sources have **not** been compiled in the delivery
    environment; the first build may surface minor Gradle/Kotlin version
    pinning adjustments on your toolchain.
