# Build/Configuration — پیکربندی نسخهٔ واحد v1.0.0-rc.1

این پوشه **تنها مرجع** پیکربندی ساخت است. نسخهٔ قدیمی و معیوب
(`windows/packaging/` با spec ارجاع‌دهنده به فایل‌های ناموجود) حذف شده و
نسخهٔ `windows/installer/` به اینجا منتقل و اصلاح شده است؛ تاریخچهٔ تصمیم در
`Documentation/BUILD.md` §5.

## cyber_workspace.spec (PyInstaller)

| مورد | مقدار |
| --- | --- |
| نقطهٔ ورود | `Source/Windows/run_app.py` (واسط نازک روی `cyber_workspace.app:main`) |
| حالت | onedir → `dist/CyberWorkspace/CyberWorkspace.exe` |
| آیکون EXE | `Source/Windows/assets/icon/cyber_workspace.ico` (16 تا 256px) |
| فایل‌های همراه | `db/schema.sql` (مستند) + `assets/icon/app_icon_256.png` (آیکون پنجره در زمان اجرا) |
| hiddenimports | PySide6 شامل QtWebEngine + آداپتور مرورگر |
| مسیرها | نسبت به `SPECPATH` محاسبه می‌شوند — محل اجرای دستور اهمیتی ندارد |

اجرا:
```powershell
pyinstaller Build/Configuration/cyber_workspace.spec --distpath dist --workpath build --noconfirm --clean
```

## cyber_workspace.iss (Inno Setup 6)

| مورد | مقدار |
| --- | --- |
| ورودی فایل‌ها | `..\..\dist\CyberWorkspace\*` |
| **خروجی Setup** | `..\..\Installer\Windows\CyberWorkspace-1.0.0-rc.1-setup.exe` |
| آیکون Setup / حذف نصب | همان `cyber_workspace.ico` + `UninstallDisplayIcon` |
| معماری | x64 فقط، نصب per-machine |

اجرا:
```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" Build\Configuration\cyber_workspace.iss
```
