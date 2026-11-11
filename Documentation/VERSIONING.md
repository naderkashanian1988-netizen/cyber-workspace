# CYBER WORKSPACE — Version & Update Strategy

## Current release

**1.0.0-rc.1** — first release candidate (2026-11-11).
Not silently branded production-ready: see TEST_REPORT.md for the
automated/target verification boundary.

## Versioning scheme

SemVer `MAJOR.MINOR.PATCH` with a pre-release tag (`-rc.N`, `-beta.N`).

- **MAJOR** — incompatible protocol or schema change; migration guide required.
- **MINOR** — new features, backwards-compatible protocol additions.
- **PATCH** — bug fixes, no wire/format changes.

Components versioned together: Windows host, Android app, protocol v1.

## Protocol compatibility (PROTOCOL.md §8)

1. Clients ignore unknown payload fields (forward-compatible minors).
2. Unknown ops are logged + ignored (`BAD_REQUEST`), never fatal to the
   engine.
3. Renaming/removing fields or changing semantics ⇒ protocol **v2**; the
   host keeps serving v1 for one minor cycle. Version is negotiated on
   connect (`welcome.protocol_version`); mismatch → clean close.
4. SQLite schema: `PRAGMA user_version` migrations in `Database._migrate`;
   each new version appends a step (never rewrites history).

## Update strategy

1. **Release artifacts**: Windows portable zip + Inno Setup EXE; Android APK.
   Sign the installer/EXE (Authenticode) and the APK (release keystore)
   before distribution; record hashes in release notes.
2. **Data safety on update**: `%APPDATA%\CyberWorkspace\workspace.db` and
   Android Room db migrate in place; a pre-update copy of the DB is the
   user's rollback path (documented in INSTALL.md).
3. **In-app update check (planned, MINOR release)**: version manifest fetched
   over HTTPS, hash-verified download, user-confirmed install — no silent
   updates, no auto-execution of downloaded binaries.
4. **Compatibility check at connect**: host rejects clients with an
   incompatible protocol version rather than degrading silently.

## Changelog

### 1.0.0-rc.1 (2026-11-11)
- Windows host: dashboard, 8-state task engine with per-task isolation,
  tri-timer (active/waiting/error/paused/unknown), SQLite persistence +
  crash recovery with process re-adoption, script/terminal/external/browser
  adapters, marker protocol (`@@CW:*@@`), notification center, system tray,
  power panel (SetThreadExecutionState keep-awake + settings pages),
  network monitor (real speeds + TCP latency), CPU/RAM monitoring,
  remote control server (TLS, pairing, tokens, audit).
- Android companion: pairing + pinning, dashboard/detail/notifications,
  approvals, local URL-monitor tasks in a foreground service.
- 45 automated tests; TEST A–J mapped in Test Reports/TESTING.md.
