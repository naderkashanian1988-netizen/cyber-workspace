# CYBER WORKSPACE — سایبر ورک‌اسپیس

**نسخه 1.0.0-rc.1 · رابط کاربری سایبری مشکی + سبز نئونی · میزبان ویندوز + همراه اندروید**

یک فضای کاری چندوظیفه‌ای واقعی و قابل‌اعتماد برای **ویندوز 10/11 x64** به‌همراه
اپلیکیشن نظارت/کنترل جفتی برای **اندروید**. هر وظیفه (اسکریپت، ترمینال، برنامهٔ
خارجی یا تب مرورگر) **چرخهٔ حیات مستقل** خودش را دارد: پروسه و زمینهٔ اجرای جدا،
ماشین وضعیت مستقل، جریان رویداد، لاگ، مدیریت خطا، تایمرها و سنجه‌های منابع.
خرابی یک وظیفه هرگز بقیه را متوقف نمی‌کند.

## آیکون برنامه (App Icon)

آیکون رسمی برنامه از تصویر «تاج» ساخته و در هر سه پلتفرم یکپارچه شد:

| پلتفرم | فایل | محل |
| --- | --- | --- |
| ویندوز (EXE و Setup) | `cyber_workspace.ico` (16 تا 256 پیکسل) | `Source/Windows/assets/icon/` |
| ویندوز (آیکون پنجره هنگام اجرا) | `app_icon_256.png` | همان پوشه + بارگذاری خودکار در `app.py` |
| اندروید (لانچر) | `ic_launcher.png` در ۵ چگالی (48/72/96/144/192) | `Source/Android/app/src/main/res/mipmap-*/` |
| اندروید (آیکون گرد) | `ic_launcher_round.png` در ۵ چگالی | همان پوشه |
| اندروید (آیکون انطباقی API 26+) | `ic_launcher_foreground.png` در ۵ چگالی (شبکهٔ 108dp) | همان پوشه |
| نسخهٔ مرجع | `app_icon_1024.png` و `app_icon_512.png` | `Source/Shared/assets/` |

## بیانیهٔ صداقت (مهم)

این مخزن **سورس کامل، اسکریپت‌های ساخت و مجموعهٔ تست خودکار** را ارائه می‌کند.
موتور اصلی، ذخیره‌سازی، تایمرها، ایزولاسیون، بازیابی و پروتکل ریموت به‌صورت
خودکار اجرا و تأیید شده‌اند (اجرای اولیه: 45/45 سبز؛ بازتأیید در محیط لینوکسی
تحویل: 44 قبولی + 1 صرف‌نظر — تست دود رابط گرافیکی به‌دلیل نبود کتابخانهٔ سیستمی
`libEGL.so.1`، شرح کامل در `Test Reports/TEST_REPORT.md`).

**فایل‌های نصب (EXE/APK) در محیط تحویل ساخته نشده‌اند** — این محیط یک سندباکس
لینوکسی است که نه ویندوز دارد، نه Android SDK و نه اعتبارنامهٔ GitHub. مسیر
ساخت واقعی: پس از انتشار مخزن روی GitHub، دو workflow آماده در
`.github/workflows/` به‌طور خودکار EXE و APK را می‌سازند و خروجی‌ها را در
همین پوشه (`Installer/`) جای‌گذاری کنید. راهنمای گام‌به‌گام:
`Documentation/GITHUB_PUSH.md`. هیچ ادعایی دربارهٔ کارکرد روی پلتفرم مقصد
در این README وجود ندارد مگر آنکه گزارش تست آن را تأیید کند.

## شروع سریع

### ویندوز (حالت توسعه)
```powershell
cd Source\Windows
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m cyber_workspace        # اجرای فضای کاری
.\.venv\Scripts\python -m pytest tests -q        # مجموعهٔ تست
```

### ویندوز (نصب‌کننده)
```powershell
powershell -ExecutionPolicy Bypass -File Build\Scripts\build_windows.ps1
# → dist\CyberWorkspace\CyberWorkspace.exe                       (نسخهٔ قابل‌حمل)
# → Installer\Windows\CyberWorkspace-1.0.0-rc.1-setup.exe        (با Inno Setup)
```

### اندروید
پروژهٔ `Source/Android/` را در Android Studio (Koala یا جدیدتر) باز کنید، یا:
```bash
cd Source/Android && gradle wrapper && ./gradlew assembleDebug
```
جفت‌سازی با میزبان ویندوز: در تنظیمات فضای کاری «Remote access» را روشن کنید،
روی **Pair new device** بزنید، سپس host:port و کد ۶ رقمی را در اپ اندروید وارد
کنید و اثر انگشت TLS را تأیید کنید. `Source/Shared/tools/remote_test_client.py`
می‌تواند کل پروتکل را بدون گوشی آزمایش کند.

## نقشهٔ مخزن (تک‌ریشه — همهٔ فایل‌ها زیر همین پوشه‌اند)

```
Source/
  Windows/            میزبان پایتون 3 + PySide6
    cyber_workspace/
      core/           موتور، ماشین وضعیت، تایمر سه‌گانه، رویدادها، مدل وظیفه
      adapters/       اسکریپت · ترمینال · برنامهٔ خارجی · مرورگر (QtWebEngine اختیاری)
      persistence/    مخازن SQLite + اسکیمای نهفته
      monitors/       CPU/RAM + شبکه (فقط اندازه‌گیری واقعی)
      platform/       مدیریت توان (SetThreadExecutionState)
      remote/         سرور TLS، جفت‌سازی، توکن‌ها، حسابرسی
      protocol/       مدل پیام پروتکل v1
      ui/             تم سایبری، داشبورد، کارت‌ها، پنل‌ها، دیالوگ‌ها، تری
    assets/icon/      آیکون ویندوز (ico + png)
    tests/            45 تست خودکار (نگاشتهاست به TEST A–J)
    db/schema.sql     اسکیمای مستند (نسخهٔ اجرایی درون‌کد است)
  Android/            همراه Kotlin + Jetpack Compose
  Backend/            README: چرا سرور جداگانه نداریم (منطق سرور در میزبان ویندوز نهفته است)
  Shared/
    protocol/         PROTOCOL.md + JSON Schema نسخهٔ v1
    tools/            remote_test_client.py (جانشین E2E برای APK)
    assets/           آیکون مرجع 1024/512
Installer/
  Windows/            خروجی setup.exe و پوشهٔ portable اینجا قرار می‌گیرد
  Android/            APK اینجا قرار می‌گیرد
Build/
  Scripts/            build_windows.ps1 · push_to_github.sh
  Configuration/      cyber_workspace.spec (PyInstaller) · cyber_workspace.iss (Inno Setup)
Documentation/        BUILD · INSTALL · SECURITY · ARCHITECTURE · DATABASE ·
                      DB_SCHEMA · PROTOCOL · USER_MANUAL · LIMITATIONS ·
                      VERSIONING · GITHUB_PUSH
Test Reports/         TESTING.md · TEST_REPORT.md
Backup/               Cyber-Workspace-Full-Backup.zip (پشتیبان کامل قابل بازیابی)
.github/workflows/    windows-build.yml · android-build.yml (ساخت EXE و APK روی GitHub)
```

## هشت وضعیت وظیفه

`RUNNING · WAITING_FOR_USER · NETWORK_WAITING · COMPLETED · ERROR ·
UNRESPONSIVE · PAUSED · UNKNOWN`

قواعد نافذ شده در کد و تست:
- هر تغییر وضعیت همیشه با ثبت دلیل همراه است؛ وقتی علت قابل تعیین مطمئن نیست،
  دلیل «قابل تعیین نبود علت» و وضعیت UNKNOWN ثبت می‌شود.
- بستن پنجره هرگز به‌تنهایی وظیفه را COMPLETED گزارش نمی‌کند
  (تست واحد: `test_close_is_never_completed`).
- صداقت تایمر: بازه‌های ناشناخته هرگز به‌عنوان کار فعال محاسبه نمی‌شوند
  (`test_unknown_never_merges_into_active`).

## نمایهٔ مستندات

1. `Documentation/GITHUB_PUSH.md` — انتشار روی GitHub، اجرای CI و دریافت EXE/APK
2. `Documentation/BUILD.md` — ساخت بازتولیدپذیر (ویندوز + اندروید) و تاریخچهٔ تصمیم‌ها
3. `Documentation/INSTALL.md` — نصب کاربر نهایی، محل داده‌ها، حذف نصب
4. `Documentation/ARCHITECTURE.md` — ماژول‌ها، نخ‌ها، جریان داده
5. `Documentation/DATABASE.md` + `DB_SCHEMA.md` — اسکیما و بازیابی
6. `Documentation/PROTOCOL.md` — پروتکل ریموت v1 (هنجاری)
7. `Documentation/USER_MANUAL.md` — تور داشبورد، نشانگرها، توان، جفت‌سازی
8. `Documentation/SECURITY.md` — مدل تهدید، جفت‌سازی، توکن‌ها
9. `Documentation/LIMITATIONS.md` — محدودیت‌های شناخته‌شده (بخوانید)
10. `Test Reports/TESTING.md` — چگونگی اجرای TEST A–J
11. `Test Reports/TEST_REPORT.md` — چه چیزی کجا قبول شد و چه چیزی نیاز به سخت‌افزار مقصد دارد
12. `Documentation/VERSIONING.md` — نسخه‌گذاری و سازگاری
