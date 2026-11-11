# CYBER WORKSPACE — Android client build & pairing guide

Android companion app for the CYBER WORKSPACE Windows host. Over a TLS channel
pinned to the host's SHA-256 certificate fingerprint it shows live task state
(five TriTimer buckets: Active / Waiting / Error / Paused / Unknown), surfaces
approval prompts (Approve / Deny), and sends control commands (Pause / Resume /
Restart / Close). Two notification channels are created: **Task updates** and
**Approvals**.

> **This app does NOT run Windows programs.** Windows execution stays on the
> Windows host. This app monitors and controls it remotely.

## 1. Prerequisites

| Tool | Expected version |
| --- | --- |
| Android Studio | Koala (2024.1.1) or newer |
| Android SDK | Platform 34 (`compileSdk 34`), `minSdk 29` |
| JDK | 17 (bundled with recent Android Studio builds) |

The authoritative versions live in the module's `app/build.gradle(.kts)`; if
this document and that file disagree, trust the Gradle files.

The resources and unit tests in this drop assume the module declares, at
minimum:

* `com.google.android.material:material` — provides the `Theme.Material3.*`
  parent used by `values/themes.xml`
* `org.jetbrains.kotlinx:kotlinx-serialization-json` — used by the protocol tests
* `junit:junit:4.13.2` (or the AndroidX test wrapper around it) — JUnit 4 tests

Because `minSdk` is 29, the adaptive icon in `mipmap-anydpi-v26/` covers every
supported device. No legacy PNG/WebP mipmaps are shipped, and nothing in this
drop references one, so there are no missing resources.

## 2. Getting a working Gradle build

The Gradle wrapper JAR (`gradle/wrapper/gradle-wrapper.jar`) is intentionally
NOT committed to the repository. Pick one:

* **Open in Android Studio (recommended):** *File → Open* the `android/`
  folder. Studio generates/syncs the wrapper and downloads the SDK pieces
  automatically.
* **Command line:** run `gradle wrapper --gradle-version 8.7` once inside
  `android/` (this needs a local Gradle installation), then use `./gradlew`
  for everything below.

## 3. Building

```bash
./gradlew assembleDebug        # debug APK
./gradlew assembleRelease      # release APK
./gradlew testDebugUnitTest    # runs ProtocolModelsTest, TriTimerTest, TlsPinningTest
```

Equivalently with a local Gradle install: `gradle assembleDebug`,
`gradle assembleRelease`.

APK output locations:

* Debug: `app/build/outputs/apk/debug/app-debug.apk`
* Release: `app/build/outputs/apk/release/` — `app-release.apk` when signed,
  `app-release-unsigned.apk` otherwise (an unsigned release build will not
  install on a device)

## 4. Pairing quick-start

1. On the **Windows host**, open CYBER WORKSPACE and choose *Show pairing
   code*. It displays a 6-digit code and the SHA-256 fingerprint of the host
   TLS certificate.
2. On this app, open **Pair with Windows workspace**, enter the host address
   and port, then the 6-digit code.
3. The app displays the fingerprint it received in `AA:BB:CC:…` form (32 hex
   pairs). Compare it character-by-character against the fingerprint shown on
   the Windows host. **Do not trust the connection unless both fingerprints
   match exactly** — that comparison is the entire point of the pinning step.
4. Once paired, the device holds either view-only or view + control
   permission, surfaced via `permission_view_note` /
   `permission_control_note` on the dashboard.

## 5. Honest limitations — read before filing bugs

* **No Windows execution on the phone.** Windows execution stays on the
  Windows host. This app monitors and controls it remotely. Nothing in this
  APK is a Windows program runner.
* **Doze / App Standby applies to local tasks.** Android may suspend local
  tasks in Doze mode; suspended intervals are reported as Unknown, never
  counted as active work. This is intentional, honest accounting — the
  dashboard shows `Unknown` time rather than guessing.
* **This source has NOT been compiled in the delivery environment.** The
  resources, tests, and docs here were written without a Gradle or toolchain
  run. Build on your machine with the steps above and treat the first sync as
  the real smoke test.
* **Protocol version 1 only.** The wire contract is documented at
  [`../Shared/protocol/PROTOCOL.md`](../Shared/protocol/PROTOCOL.md). Envelopes with `v != 1` are
  rejected by the version gate; unknown `op` strings are carried as opaque
  strings so newer hosts degrade gracefully on older clients.

## 6. What was delivered in this drop

| Path | Purpose |
| --- | --- |
| `app/src/main/res/values/strings.xml` | Every user-facing string, including the Doze and remote-execution honesty notes |
| `app/src/main/res/values/themes.xml` | `Theme.CyberWorkspace` (Material3 DayNight, NoActionBar, `#0A0C0A` window/status bar) |
| `app/src/main/res/mipmap-*/ic_launcher.png` | Raster launcher icon (crown on `#0A0C0A`-family neon backdrop): 48/72/96/144/192 px |
| `app/src/main/res/mipmap-*/ic_launcher_foreground.png` | Adaptive-icon foreground layer (108 dp grid, crown in safe zone) |
| `app/src/main/res/mipmap-*/ic_launcher_round.png` | Raster round launcher icon (circular mask) |
| `app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml` | Adaptive icon wiring |
| `app/src/main/res/mipmap-anydpi-v26/ic_launcher_round.xml` | Adaptive round-icon wiring |
| `app/src/test/kotlin/com/cyberworkspace/app/ProtocolModelsTest.kt` | Self-contained protocol v1 envelope tests (local `@Serializable` mirrors, version gate) |
| `app/src/test/kotlin/com/cyberworkspace/app/TriTimerTest.kt` | Self-contained five-bucket timer tests (injected clock, freeze, orphan recovery) |
| `app/src/test/kotlin/com/cyberworkspace/app/TlsPinningTest.kt` | SHA-256 fingerprint formatting + verifier tests |
