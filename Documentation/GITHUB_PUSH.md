# انتشار مخزن روی GitHub، اجرای CI و دریافت خروجی‌های واقعی

این سند دقیقاً همان «مرحلهٔ نهایی» است: انتشار → ساخت EXE و APK روی
GitHub Actions → جای‌گذاری خروجی‌ها در `Installer/` → به‌روزرسانی پشتیبان.

## ۰. وضعیت صادقانهٔ محیط تحویل

سندباکس لینوکسیِ تحویل به اینترنت دسترسی دارد اما **هیچ اعتبارنامه‌ای برای
حساب GitHub شما ندارد** (نه توکن، نه کلید SSH، نه gh CLI). بنابراین انتشار
باید با یک توکن که **خودتان** می‌سازید انجام شود — با یک دستور یا با دستورات
دستی، هر دو آماده است. هیچ راز/کلیدی در مخزن وجود ندارد (`*.pem`, `*.key`,
`*.keystore` در `.gitignore` ریشه رد شده‌اند).

## ۱. ساخت توکن (یک‌بار، روی مرورگر)

1. وارد GitHub شوید → Settings → Developer settings → **Personal access tokens → Fine-grained**.
2. Generate new token، فقط روی مخزن مقصد، مجوز **Contents: Read and write** (برای ساخت مخزن: **Administration: Read and write**).
3. توکن را کپی کنید. توکن را در هیچ فایلی ذخیره نکنید.

## ۲. انتشار با یک دستور (پیشنهادی)

از ریشهٔ مخزن (`Cyber Workspace/`)، در لینوکس/مک/WSL/Git-Bash:

```bash
GITHUB_TOKEN=ghp_xxxxxxxxxxxx bash Build/Scripts/push_to_github.sh <نام‌کاربری‌گیت‌هاب> cyber-workspace
```

اسکریپت چه می‌کند؟
1. با API گیت‌هاب مخزن `cyber-workspace` را می‌سازد (اگر از قبل باشد، ۴۲۲ را می‌پذیرد و ادامه می‌دهد).
2. remote با URL **تمیز** (بدون توکن) اضافه می‌کند؛ توکن فقط در همان یک فراخوانِ push استفاده و ذخیره نمی‌شود.
3. شاخهٔ `main` را push می‌کند → هر دو workflow (`windows-build`، `android-build`) بلافاصله اجرا می‌شوند.

## ۲.جایگزین. انتشار دستی

```bash
cd "Cyber Workspace"
git remote add origin https://github.com/<نام‌کاربری>/cyber-workspace.git
git push -u origin main          # نام کاربری + توکن را می‌پرسد
```

## ۳. اجرای workflowها

- پس از push، هر دو workflow خودکار اجرا می‌شوند.
- اجرای مجدد/دستی: تب **Actions** → workflow را انتخاب → **Run workflow**.
- `windows-build`: تست‌ها → PyInstaller (آیکون تعبیه‌شده) → Inno Setup → دو artifact:
  `CyberWorkspace-portable` و `CyberWorkspace-installer`.
- `android-build`: تست‌های واحد → `assembleDebug` → artifact: `CyberWorkspace-remote-debug-apk`.

## ۴. جای‌گذاری خروجی‌ها در پوشهٔ اصلی

از تب Actions → اجرای موفق → بخش Artifacts دانلود کنید و دقیقاً اینجا بگذارید:

| artifact دانلودی | مقصد در این پوشه |
| --- | --- |
| `CyberWorkspace-installer` (فایل `CyberWorkspace-1.0.0-rc.1-setup.exe`) | `Installer/Windows/` |
| `CyberWorkspace-portable` (کل پوشهٔ `CyberWorkspace/`) | `Installer/Windows/portable/` (اختیاری؛ زیپ کنید) |
| `CyberWorkspace-remote-debug-apk` (فایل `app-debug.apk`) | `Installer/Android/` (نام را به `cyber-workspace-remote-debug.apk` تغییر دهید) |

## ۵. به‌روزرسانی ZIP پشتیبان

پس از جای‌گذاری خروجی‌ها، پشتیبان را بازتولید کنید (از ریشهٔ مخزن):

```bash
cd "Cyber Workspace"
python3 - <<'PY'
import zipfile, pathlib
root = pathlib.Path('.')
out  = root / 'Backup' / 'Cyber-Workspace-Full-Backup.zip'
out.parent.mkdir(exist_ok=True)
skip = {'__pycache__', '.git', '.pytest_cache', '.venv', 'build', 'dist', '.gradle'}
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    for p in sorted(root.rglob('*')):
        if any(s in p.parts for s in skip) or p == out or not p.is_file():
            continue
        z.write(p, p.as_posix())
print('backup written:', out)
PY
```

(همین کار در محیط تحویل با `scripts/rebuild_backup.py` انجام شده؛ الگوی یکسان است.)

## ۶. چک‌لیست نهایی تحویل

- [ ] مخزن روی GitHub و شاخهٔ main همگام
- [ ] Actions: هر دو workflow سبز
- [ ] `Installer/Windows/` شامل setup.exe
- [ ] `Installer/Android/` شامل APK
- [ ] `Backup/Cyber-Workspace-Full-Backup.zip` بازتولیدشده و تست‌پذیر
- [ ] فایل ضروری‌ای بیرون از پوشهٔ `Cyber Workspace/` باقی نمانده
