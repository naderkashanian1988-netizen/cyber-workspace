# Build — خط لولهٔ ساخت

همهٔ چیزِ لازم برای تولید خروجی‌های واقعی، در دو زیرپوشه:

| زیرپوشه | محتوا | نقش |
| --- | --- | --- |
| `Scripts/` | `build_windows.ps1` · `push_to_github.sh` | اجرای خط لولهٔ ویندوز؛ انتشار مخزن روی GitHub |
| `Configuration/` | `cyber_workspace.spec` · `cyber_workspace.iss` | پیکربندی PyInstaller و Inno Setup — نسخهٔ واحد و نهایی v1.0.0-rc.1 |

و workflowهای CI در `.github/workflows/` ریشهٔ مخزن:
`windows-build.yml` (EXE) و `android-build.yml` (APK).

## جریان کامل ساخت ویندوز

```
Build\Scripts\build_windows.ps1
  ├─ 1. venv + requirements.txt (نسخه‌های پین‌شده)
  ├─ 2. گیت تست pytest — شکست تست = انصراف از ساخت
  ├─ 3. PyInstaller با Build\Configuration\cyber_workspace.spec
  │      (آیکون ico در EXE تعبیه می‌شود؛ onedir)
  └─ 4. Inno Setup با Build\Configuration\cyber_workspace.iss
         → Installer\Windows\CyberWorkspace-1.0.0-rc.1-setup.exe
```

## جریان ساخت اندروید

```
cd Source/Android
gradle :app:testDebugUnitTest   # تست‌های واحد
gradle :app:assembleDebug       # → app/build/outputs/apk/debug/app-debug.apk
```
(gradle wrapper عمداً به مخزن اضافه نشده؛ CI با `gradle/actions/setup-gradle`
نسخهٔ 8.7 — منطبق با `gradle-wrapper.properties` — را نصب می‌کند.)

## بیانیهٔ صداقت

در سندباکس لینوکسیِ تحویل، هیچ‌کدام از این خطوط لوله اجرا نشده‌اند
(نه ویندوز، نه Android SDK). اسکریپت‌ها مسیر مشخص و پین‌شده دارند و
تاریخچهٔ تصمیم‌های ساخت در `Documentation/BUILD.md` §5 ثبت است.
