# Installer/Windows — محل خروجی نصب ویندوز

**این پوشه عمداً خالی نگه داشته می‌شود** و محل ورود «خروجی‌های واقعی ساخت» است.

## چه فایل‌هایی اینجا قرار می‌گیرند؟

| فایل | ساخته‌شده توسط | راهنما |
| --- | --- | --- |
| `CyberWorkspace-1.0.0-rc.1-setup.exe` | Inno Setup (اسکریپت `Build/Configuration/cyber_workspace.iss` خودش خروجی را به همین پوشه می‌نویسد) | `Documentation/GITHUB_PUSH.md` §۴ |
| `CyberWorkspace-portable.zip` (اختیاری، دستی) | زیپ‌شدهٔ `dist/CyberWorkspace/` پس از PyInstaller | همان سند |

## دو راه تولید

1. **روی خود ویندوز:** `powershell -ExecutionPolicy Bypass -File Build\Scripts\build_windows.ps1`
   (نیازمند پایتون 3.10+؛ برای setup نیز Inno Setup 6).
2. **روی GitHub CI:** پس از انتشار مخزن، workflow `windows-build` خروجی را به‌صورت
   artifact می‌دهد؛ آن را دانلود و در همین پوشه کپی کنید.

## بیانیهٔ صداقت

در محیط تحویل (سندباکس لینوکسی، بدون ویندوز) هیچ EXE‌ای ساخته نشده و چیزی که
اینجا نیست، ادعایی هم برایش نمی‌شود. تا زمان اجرای CI یا build محلی، این پوشه
خالی می‌ماند.
