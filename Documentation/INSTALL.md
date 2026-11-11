# CYBER WORKSPACE — Installation Guide

## Windows 10/11 x64

### Option A — installer (recommended)
1. Run `CyberWorkspace-1.0.0-rc.1-setup.exe` (built per BUILD.md).
2. Follow the wizard (per-machine install, optional desktop icon).
3. Launch **CYBER WORKSPACE** from the Start menu. The neon tray icon appears;
   the dashboard opens.

### Option B — portable
1. Copy the `CyberWorkspace\` folder anywhere.
2. Run `CyberWorkspace.exe`. No services, no drivers, no admin rights needed.

### Option C — from source
See BUILD.md §1.

### Data locations
| What | Where |
| --- | --- |
| Database, settings, TLS key material | `%APPDATA%\CyberWorkspace\` |
| Task logs | in the database (`task_events`) and each card's detail view |

### Requirements
- WebView/browser tasks additionally require the QtWebEngine module of
  PySide6 (bundled in the PyInstaller build; in dev installs it is part of
  the pinned `PySide6==6.12.0` requirement).
- Python script tasks use the machine's Python or a custom interpreter path.

### Uninstall
Standard "Apps & features" uninstall. `%APPDATA%\CyberWorkspace\` is kept on
purpose (sessions/history) — delete it manually for a full wipe.

## Android 10+

1. Build the APK per BUILD.md §2 and install it
   (`adb install app-debug.apk` or open the file on the device).
2. First launch → **Pair with Windows workspace**:
   - On Windows: Settings → enable *Remote access* → 🔑 **Pair new device** →
     a 6-digit code (valid 5 min, single use) is shown with the TLS
     fingerprint.
   - On Android: enter `host:port`, the code, and the device name.
   - Verify the fingerprint shown on the phone **matches** the Windows screen,
     tick the confirmation, and connect.
3. The dashboard shows your Windows task cards; approvals can be answered from
   the phone (devices have view+control permission by default; revoke anytime
   from the Windows Devices dialog).

### Permissions the app requests
| Permission | Why |
| --- | --- |
| INTERNET | WSS connection to your Windows host (LAN) |
| POST_NOTIFICATIONS | task/approval notifications (Android 13+ asks at runtime) |
| FOREGROUND_SERVICE (+ dataSync) | runs **local** URL-monitor tasks reliably while used |
| ACCESS_NETWORK_STATE | honest network-state reporting for local tasks |

### Security notes
- Pairing is mandatory; the app refuses unauthenticated connections, and the
  server refuses unauthenticated commands.
- Tokens live in Android `EncryptedSharedPreferences`; the server stores only
  SHA-256 hashes. Sessions expire after 30 unused days (re-pair then).
- Revoke a lost device from the Windows **📱 Devices** dialog — access ends
  immediately.

## Firewall

Allow inbound TCP on the configured remote port (default **47770**) on the
Windows machine for the LAN, or restrict to the specific device IP. The
server binds `0.0.0.0` by default — change it in Settings if you want
loopback-only testing.
