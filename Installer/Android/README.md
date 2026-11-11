# Installer/Android — محل خروجی APK

**این پوشه عمداً خالی نگه داشته می‌شود** و محل ورود «خروجی واقعی ساخت» است.

## چه فایلی اینجا قرار می‌گیرد؟

| فایل | ساخته‌شده توسط | راهنما |
| --- | --- | --- |
| `cyber-workspace-remote-debug.apk` | workflow `android-build` روی GitHub (gradle `:app:assembleDebug`) | `Documentation/GITHUB_PUSH.md` §۴ |
| نسخهٔ release (اختیاری) | `gradle :app:assembleRelease` با keystore خودتان — کلید هرگز به مخزن راه نمی‌یابد | `Documentation/SECURITY.md` |

## نصب روی گوشی

APK را به گوشی منتقل کنید و نصب کنید (اجازهٔ «نصب از منابع ناشناس» لازم است؛
نسخهٔ debug برای آزمایش است، نه توزیع عمومی).

## بیانیهٔ صداقت

در محیط تحویل (سندباکس لینوکسی، بدون Android SDK) هیچ APK‌ای ساخته نشده است.
اپ اندروید در `Source/Android/` کامل است (Kotlin + Compose + تست‌های واحد) و
workflow آمادهٔ ساخت دارد؛ خروجی پس از اجرای CI به این پوشه اضافه می‌شود.
