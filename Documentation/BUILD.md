# CYBER WORKSPACE — Build Instructions (reproducible)

All versions are pinned (`Source/Windows/requirements.txt`, gradle files).
Builds are deterministic w.r.t. those inputs; PyInstaller/Gradle artifacts are
not bit-for-bit reproducible, but the same inputs always produce functionally
identical outputs. Record tool versions in your release notes.

## 1. Windows application

Prerequisites: Windows 10/11 x64, Python 3.10+ (3.12 recommended), PowerShell.

### Development run
```powershell
cd Source\Windows
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m pytest tests -q     # suite must be green
.\.venv\Scripts\python -m cyber_workspace
```

### Full pipeline (tests → frozen app → installer)
```powershell
powershell -ExecutionPolicy Bypass -File Build\Scripts\build_windows.ps1
```
Steps performed:
1. fresh venv + pinned `Source/Windows/requirements.txt`
2. **pytest gate** — a failing suite aborts the build
3. PyInstaller 6.11.1 with `Build/Configuration/cyber_workspace.spec`
   (onedir, WebEngine included, schema.sql bundled, **app icon embedded**)
4. Inno Setup 6 with `Build/Configuration/cyber_workspace.iss` when ISCC is
   present → **`Installer/Windows/CyberWorkspace-1.0.0-rc.1-setup.exe`**

Outputs:
- portable: `dist/CyberWorkspace/CyberWorkspace.exe` (+ `_internal/`)
- installer: setup EXE, x64, per-machine install, crowned app icon

To add a code-signing step, sign `CyberWorkspace.exe` and the setup EXE with
your certificate before distribution (see SECURITY.md §7).

## 2. Android application

Prerequisites: Android Studio Koala+ (or Gradle 8.7 + SDK 34 + JDK 17).

```bash
cd Source/Android
gradle wrapper                 # wrapper JAR is intentionally NOT committed
./gradlew testDebugUnitTest    # JVM unit tests (protocol, tri-timer, pinning)
./gradlew assembleDebug        # app/build/outputs/apk/debug/app-debug.apk
./gradlew assembleRelease      # add your signing config for distribution
```

Pins: AGP 8.5.2 · Kotlin 2.0.20 · compileSdk 34 · minSdk 29 · targetSdk 34 ·
Compose BOM 2024.09.03 · Room 2.6.1 (KSP) · OkHttp 4.12.0 · Gradle 8.7.

## 3. Building on GitHub CI (no local toolchain needed)

Two workflows ship with the repository (`.github/workflows/`):

| Workflow | Runner | Produces (artifacts) |
| --- | --- | --- |
| `windows-build` | `windows-latest` | `CyberWorkspace-portable`, `CyberWorkspace-installer` |
| `android-build` | `ubuntu-latest` | `CyberWorkspace-remote-debug-apk` (+ unit-test results) |

Both trigger on push to `main`, on tags `v*`, and manually
(`workflow_dispatch`). The exact publish → download → place-into-`Installer/`
procedure is documented step by step in `GITHUB_PUSH.md`.

## 4. App icon (integrated everywhere)

Source image: user-supplied crown artwork. Generated set (single visual
identity, theme colours `#0A0C0A` + `#00FF66`):

| Surface | File | Wired by |
| --- | --- | --- |
| Windows EXE | `Source/Windows/assets/icon/cyber_workspace.ico` (16–256 px) | `icon=` in the PyInstaller spec |
| Windows setup | same ico | `SetupIconFile` / `UninstallDisplayIcon` in the .iss |
| Windows window (runtime) | `Source/Windows/assets/icon/app_icon_256.png` | `app.setWindowIcon()` in `cyber_workspace/app.py` (bundled via spec `datas`) |
| Android launcher | `Source/Android/app/src/main/res/mipmap-*/ic_launcher.png` (48/72/96/144/192) | `android:icon="@mipmap/ic_launcher"` (manifest) |
| Android round | `mipmap-*/ic_launcher_round.png` | `android:roundIcon` slot / launcher |
| Android adaptive (API 26+) | `mipmap-*/ic_launcher_foreground.png` + `drawable/ic_launcher_background.xml` | `mipmap-anydpi-v26/ic_launcher*.xml` |
| Master/reference | `Source/Shared/assets/app_icon_1024.png`, `app_icon_512.png` | documentation, store listing |

The 1024 px master is upscaled from a 413 px original (LANCZOS) — honest
note: it is sharp at launcher sizes, but not a native-resolution redraw.

## 5. Build-configuration consolidation decision (history)

Earlier drops carried **two competing packaging folders**
(`windows/packaging/` and `windows/installer/`). The `packaging/` copy was
broken (its spec referenced files that do not exist — e.g. a
`storage/schema.sql` path and a stale entry point) and pinned an older
version. Decision (recorded here since v1.0.0-rc.1):

- `windows/packaging/` was **deleted**; `windows/installer/` contents were
  **moved to `Build/Configuration/`** (spec + iss) and `Build/Scripts/`
  (build_windows.ps1), upgraded to v1.0.0-rc.1, CWD-independent (spec paths
  resolve via `SPECPATH`) and icon-wired.
- The Inno Setup output was redirected to `Installer/Windows/` so CI and
  local builds drop their artifacts into the delivery folder directly.
- All references across docs, scripts and code comments were re-pointed and
  asserted zero stale leftovers.

## 6. Delivery environment disclosure

This source tree was produced and verified in a Linux sandbox:
- Windows **core logic, persistence, timers, isolation, recovery, protocol
  and the UI in offscreen mode** were executed and tested there (original
  run 45/45; re-verification 44 passed + 1 environmental skip — see
  `Test Reports/TEST_REPORT.md`).
- The Windows installer and the APK **were not built** in the sandbox (no
  Windows toolchain, no Android SDK, no GitHub credentials). The scripts in
  §1–2 are the reproducible path on target machines; §3 is the reproducible
  path without any local toolchain. See TEST_REPORT.md for the exact boundary.

## 7. Verify your build

```powershell
# Windows, after install:
CyberWorkspace.exe
# → crowned icon in taskbar/tray, dashboard opens, "engine ready" in status bar
python Source\Shared\tools\remote_test_client.py pair --host <LAN-IP> --port 47770 --code <code>
# → pairing_ok + credentials, then `watch`/`command` subcommands
```
```bash
adb install Source/Android/app/build/outputs/apk/debug/app-debug.apk
```
