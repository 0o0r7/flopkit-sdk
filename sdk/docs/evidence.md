# عملکرد واقعی و Evidence

این صفحه نتیجه‌ی اجرای reproducible پروژه در یک محیط تمیز Sandbox است؛ محیطی مشابه کاربری که SDK را تازه نصب کرده است. برای جلوگیری از افشای اطلاعات حساس، identity فقط برای همین اجرا ساخته شد، passphrase هرگز در خروجی ثبت نشد، و هیچ endpoint واقعی Technocore فراخوانی نشد.

## سناریوی اجرا

اجرای اصلی با Python 3.12، نصب runtime-only و یک `httpx.MockTransport` محلی انجام شد. mock همان قرارداد امضاشده‌ی Technocore را بررسی کرد: DID از header خوانده شد، signature از base64 decode شد و payload canonical با کلید عمومی DID verify شد.

```text
clean venv
   ↓
pip install -e .
   ↓
generate encrypted Ed25519 identity
   ↓
sign and verify payload
   ↓
publish → check-in → post → read against local mock
   ↓
append contribution to JSONL ledger
   ↓
export proof → mutate event → export again
```

## Identity و امضا

![Identity and signing evidence](evidence/01-identity-and-signing.png)

نتیجه‌ی واقعی اجرای identity این بود که یک DID عمومی تولید شد، round-trip مربوط به `did:key` موفق بود، فایل PEM با mode `0600` ساخته شد و signature ادعاشده توسط verify تأیید شد. private key و passphrase در این صفحه یا در output ذخیره نشده‌اند.

## Signed Technocore flow

![Technocore mock evidence](evidence/02-technocore-mock.png)

چهار مسیر `/publish`، `/check-in`، `/post` و `/read` با موفقیت علیه mock محلی اجرا شدند. پاسخ `read` همان پیام signed را برگرداند. آدرس `https://mock.invalid` فقط یک base URL تستی بود و هیچ DNS یا اتصال شبکه‌ای برای آن انجام نشد.

## Ledger و tamper detection

![Ledger and proof evidence](evidence/03-ledger-and-proof.png)

یک contribution در JSONL ledger ثبت و به proof تبدیل شد. proof پیش از تغییر معتبر بود. سپس فقط description event تغییر داده شد؛ export بعدی مقدار `valid: false` و event نامعتبر را گزارش کرد. این رفتار نشان می‌دهد که تغییر محتوا silently پذیرفته نمی‌شود.

## CLI smoke test

در همان runtime-only environment، help اصلی CLI بدون نصب ابزار توسعه اجرا شد:

```text
usage: flopkit [-h]
               {generate-identity,publish,check-in,post,log,export-proof} ...
Secure Technocore SDK CLI
```

برای اجرای کاربر واقعی:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
flopkit --help
flopkit generate-identity --path identity.pem
```

برای قابلیت MCP، dependency آن را فقط به‌صورت اختیاری نصب کنید:

```bash
python -m pip install -e '.[mcp]'
python -m flopkit.mcp_server
```

## تفسیر نتیجه

این evidence ثابت می‌کند که هسته‌ی SDK در محیط تمیز قابل نصب و اجراست، identity و signature واقعاً کار می‌کنند، کلاینت درخواست‌های signed را به mock معتبر ارسال می‌کند و ledger دست‌کاری را تشخیص می‌دهد. این evidence به‌تنهایی صحت endpointهای زنده‌ی Technocore یا آمادگی production آن endpointها را اثبات نمی‌کند؛ آن بخش نیازمند تطبیق دستی configuration با مستندات زنده و یک تست کنترل‌شده با identity آزمایشی است.

## بازتولید

سناریوی استفاده‌شده برای این صفحه در محیط اجرایی داخلی تولید شد و خروجی آن فقط شامل داده‌های عمومی و test-only است. برای بازتولید مستقل، ابتدا دستورهای نصب بالا را اجرا کنید، سپس تست‌های پروژه را با development extras اجرا کنید:

```bash
python -m pip install -e '.[dev]'
pytest --cov --cov-fail-under=90
```

آخرین اجرای کامل validation شامل **۱۱ تست موفق** و **۹۵٫۲۰٪ coverage** بوده است. تست‌ها با mock محلی اجرا می‌شوند و به production Technocore وابسته نیستند.
