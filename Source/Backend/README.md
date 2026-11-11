# Source/Backend — توضیح معماری

**این پوشه عمداً خالی است و کدی ندارد — این یک تصمیم معماری است، نه سهوی.**

## چرا سرور بک‌اند جداگانه وجود ندارد؟

منطق سمت سرور (کل سامانهٔ ریموت‌کنترل) **عمداً درون خود میزبان ویندوز نهفته
است** و به سرویس ابری جداگانه‌ای نیاز ندارد:

| نقش سرور | محل پیاده‌سازی (درون میزبان ویندوز) |
| --- | --- |
| سرور WebSocket + TLS | `Source/Windows/cyber_workspace/remote/server.py` |
| ساخت گواهی و اثر انگشت TLS | `Source/Windows/cyber_workspace/remote/certgen.py` |
| جفت‌سازی دستگاه با کد ۶ رقمی + PIN | `Source/Windows/cyber_workspace/remote/pairing.py` |
| توکن‌ها و احراز هویت | `Source/Windows/cyber_workspace/remote/auth.py` |
| مدل پیام‌های wire | `Source/Windows/cyber_workspace/protocol/messages.py` (قرینهٔ اندروید: `Source/Android/.../protocol/ProtocolModels.kt`) |

مزیت‌ها: داده‌ها هرگز از شبکهٔ محلی خارج نمی‌شوند، هیچ سرور مرکزی و حساب
کاربری لازم نیست، و زنجیرهٔ اعتماد فقط بین «میزبان جفتی‌شده» و «گوشی جفتی‌شده»
برقرار است (TLS + اثر انگشت سنجاق‌شده). شرح امنیتی کامل:
`Documentation/SECURITY.md`؛ شرح معماری: `Documentation/ARCHITECTURE.md`.

## قرارداد مشترک بین دو پلتفرم

قرارداد سیمی (wire contract) در `Source/Shared/protocol/` نگهداری می‌شود
(`PROTOCOL.md` + `protocol-v1.json`) و ابزار آزمون پروتکل در
`Source/Shared/tools/remote_test_client.py` است. آیکون مرجع برنامه نیز در
`Source/Shared/assets/` قرار دارد.

## بیانیهٔ صداقت

این پوشه هیچ کد اجرایی‌ای ندارد؛ هر چیزی که «سرور» نامیده می‌شود در
`Source/Windows/cyber_workspace/remote/` اجرا می‌شود و همان‌جا تست شده است.
