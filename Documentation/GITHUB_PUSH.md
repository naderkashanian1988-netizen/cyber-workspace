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

## ۴ و ۵. جای‌گذاری خروجی‌ها + به‌روزرسانی ZIP پشتیبان (یک دستور)

پس از سبز شدن هر دو workflow، کل مرحلهٔ «دریافت خروجی واقعی → جای‌گذاری در
`Installer/` → بازتولید پشتیبان» با یک دستور انجام می‌شود:

```bash
GITHUB_TOKEN=ghp_xxxxxxxxxxxx bash Build/Scripts/fetch_artifacts.sh <نام‌کاربری‌گیت‌هاب> cyber-workspace
```

اسکریپت چه می‌کند؟
1. آخرین اجرای موفق `windows-build` و `android-build` روی `main` را پیدا می‌کند.
2. سه artifact را دانلود و دقیقاً سر جای خود می‌گذارد:

| artifact | مقصد نهایی |
| --- | --- |
| `CyberWorkspace-installer` (`*-setup.exe`) | `Installer/Windows/` |
| `CyberWorkspace-portable` (پوشهٔ `CyberWorkspace/`) | `Installer/Windows/portable/` |
| `CyberWorkspace-remote-debug-apk` (`app-debug.apk`) | `Installer/Android/cyber-workspace-remote-debug.apk` |

3. `Backup/Cyber-Workspace-Full-Backup.zip` را **با خروجی‌ها درونش** بازتولید
   می‌کند (فایل‌های کلاس راز مستثنا هستند) و تعداد فایل + SHA-256 چاپ می‌کند.

فقط بازتولید پشتیبان (بدون شبکه/توکن):

```bash
bash Build/Scripts/fetch_artifacts.sh --backup-only
```

### جای‌گذاری دستی (جایگزین)

از تب Actions → اجرای موفق → بخش Artifacts دانلود کنید و طبق جدول بالا بگذارید.


## ۶. چک‌لیست نهایی تحویل

- [ ] مخزن روی GitHub و شاخهٔ main همگام (بند ۲)
- [ ] Actions: هر دو workflow سبز
- [ ] `bash Build/Scripts/fetch_artifacts.sh …` اجرا شده →
      `Installer/Windows/` شامل setup.exe و portable، `Installer/Android/` شامل APK
- [ ] `Backup/Cyber-Workspace-Full-Backup.zip` بازتولیدشده و تست‌پذیر
- [ ] فایل ضروری‌ای بیرون از پوشهٔ `Cyber Workspace/` باقی نمانده

## ۷. آیکون برنامه

آیکون اصلی، تصویر تاج (`Source/Shared/assets/crown-source.png`) است و در کل
زنجیره اعمال شده: `app_icon_1024/512/256.png`، ویندوز `cyber_workspace.ico`
(۱۶ تا ۲۵۶ پیکسل، تعبیه‌شده در exe و نصاب)، و اندروید `mipmap-*` در همهٔ
چگالی‌ها + آیکون تطبیقی (adaptive). نیازی به کار اضافه نیست.
