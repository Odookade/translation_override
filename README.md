# Translation Override (Odoo 19)

[English](#english) | [فارسی](#فارسی)

---

## English

Fix wrong or conflicting Odoo translations from the user interface, without
editing any `.po` file.

### Installation
1. Copy the `translation_override` folder into your `addons_path`.
2. *Apps › Update Apps List*, then install **Translation Override**.
3. Enable the developer mode, then open
   **Settings › Translations › Translation Overrides**.

### Override types

| Type | What it changes | How it is applied |
|---|---|---|
| Python Code | `_()` strings: error messages, wizards, notifications... | At runtime, with priority over the `.po` files |
| Web Client | `_t()` strings of the JavaScript client | Injected in the translations sent to the browser |
| Field Label | `ir.model.fields.field_description` | Written on the record translation |
| Selection Value | `ir.model.fields.selection.name` | Written on the record translation |
| View Text | buttons, labels, help texts of a view (`arch_db`) | Term-by-term, through `update_field_translations` |
| Menu Name | `ir.ui.menu.name` | Written on the record translation |
| Window Action Name | `ir.actions.act_window.name` (page title / breadcrumb) | Written on the record translation |

### Usage
* **Find Source Text**: type the text you see on screen and pick the language.
  The tool searches menus, actions, field labels, selection values, view texts
  and the Python/JavaScript translations of the installed modules. Then click
  **Create Override** on the right result: the form is prefilled.
* **Python Code / Web Client**: the source text is the exact English string of
  the code (case sensitive). Leave *Module* empty to apply the override to
  every module. Changes are applied immediately on every worker, without
  restarting the server (users may need to reload the page).
* **View Text**: enter the text exactly as it is currently displayed in the
  chosen language (it may be the current wrong translation).

### Behaviour
* The previous value of a database target is saved, and restored when the
  override is **archived or deleted**.
* When translations are (re)loaded (module install/upgrade, language
  activation, *Load a Translation*...), overrides are **re-applied
  automatically**. The **Re-apply** button/action does it manually.
* Only one active override per target and language is allowed.
* Duplicating an override creates an archived copy.

### Limitations
* Python strings are never translated into English by Odoo (the source is
  returned directly), so a *Python Code* override can not target `en_US`.
* The Python code path relies on the internal
  `odoo.tools.translate.CodeTranslations` class. Run the tests after every
  Odoo update:
  `odoo-bin -d <db> -u translation_override --test-enable --test-tags=/translation_override --stop-after-init`
* When exporting the translations of a module (*Export Translation*), the
  values of active *Python Code* overrides are exported as its translations.

---

## فارسی

<div dir="rtl">

با این ماژول می‌توانید ترجمه‌های نادرست یا متضاد اودو را از داخل رابط کاربری
اصلاح کنید، بدون اینکه به فایل‌های `.po` دست بزنید.

### نصب
۱. پوشه‌ی `translation_override` را در یکی از مسیرهای `addons_path` کپی کنید.
۲. از منوی *برنامه‌ها › به‌روزرسانی فهرست برنامه‌ها*، ماژول **Translation Override** را نصب کنید.
۳. حالت توسعه‌دهنده را فعال کنید و به منوی
**تنظیمات › ترجمه‌ها › بازنویسی ترجمه‌ها** بروید.

### انواع بازنویسی

| نوع | چه چیزی را تغییر می‌دهد | نحوه‌ی اعمال |
|---|---|---|
| کد پایتون | رشته‌های `_()`: پیام‌های خطا، ویزاردها، اعلان‌ها و ... | هنگام اجرا، با اولویت بالاتر از فایل‌های `.po` |
| وب‌کلاینت | رشته‌های `_t()` در جاوااسکریپت | تزریق در ترجمه‌هایی که به مرورگر ارسال می‌شود |
| برچسب فیلد | `ir.model.fields.field_description` | نوشتن در ترجمه‌ی همان رکورد |
| گزینه‌ی Selection | `ir.model.fields.selection.name` | نوشتن در ترجمه‌ی همان رکورد |
| متن ویو | دکمه‌ها، برچسب‌ها و راهنماهای یک ویو (`arch_db`) | جمله به جمله، با `update_field_translations` |
| نام منو | `ir.ui.menu.name` | نوشتن در ترجمه‌ی همان رکورد |
| نام اکشن پنجره | `ir.actions.act_window.name` (عنوان صفحه / breadcrumb) | نوشتن در ترجمه‌ی همان رکورد |

### نحوه‌ی استفاده
* **یافتن متن مبدا**: متنی را که روی صفحه می‌بینید وارد کنید و زبان را انتخاب
کنید. این ابزار در منوها، اکشن‌ها، برچسب فیلدها، گزینه‌های Selection، متن ویوها
و ترجمه‌های پایتون/جاوااسکریپت ماژول‌های نصب‌شده جستجو می‌کند. سپس روی
**ساخت بازنویسی** کنار نتیجه‌ی درست کلیک کنید تا فرم به‌صورت خودکار پر شود.
* **کد پایتون / وب‌کلاینت**: متن مبدا، رشته‌ی دقیق انگلیسی داخل کد است (حساس به
حروف بزرگ و کوچک). اگر فیلد *ماژول* را خالی بگذارید، بازنویسی روی همه‌ی ماژول‌ها
اعمال می‌شود. تغییرات بلافاصله و روی همه‌ی workerها، بدون ری‌استارت سرور اعمال
می‌شوند (ممکن است کاربران نیاز به بارگذاری مجدد صفحه داشته باشند).
* **متن ویو**: متن را دقیقاً همان‌طور که الان در زبان انتخاب‌شده روی صفحه دیده
می‌شود وارد کنید (ممکن است همان ترجمه‌ی نادرست فعلی باشد).

### رفتار ماژول
* مقدار قبلی هدف ذخیره می‌شود و هنگام **بایگانی یا حذف** بازنویسی، بازگردانده می‌شود.
* هر بار که ترجمه‌ها دوباره بارگذاری شوند (نصب یا ارتقای ماژول، فعال‌سازی زبان،
*بارگذاری ترجمه* و ...)، بازنویسی‌ها **خودکار دوباره اعمال می‌شوند**. دکمه/اکشن
**اعمال مجدد** همین کار را به‌صورت دستی انجام می‌دهد.
* برای هر هدف و هر زبان فقط یک بازنویسی فعال مجاز است.
* کپی گرفتن از یک بازنویسی، یک نسخه‌ی بایگانی‌شده می‌سازد.

### محدودیت‌ها
* اودو رشته‌های پایتون را هیچ‌وقت به انگلیسی ترجمه نمی‌کند (خود متن مبدا برگردانده
می‌شود)، بنابراین بازنویسی *کد پایتون* برای زبان `en_US` ممکن نیست.
* مسیر کد پایتون به کلاس داخلی `odoo.tools.translate.CodeTranslations` وابسته است.
بعد از هر به‌روزرسانی اودو، تست‌ها را اجرا کنید (دستور در بخش انگلیسی).
* هنگام خروجی گرفتن از ترجمه‌های یک ماژول (*Export Translation*)، مقدار بازنویسی‌های
فعال *کد پایتون* به‌عنوان ترجمه‌ی آن ماژول خروجی گرفته می‌شود.

</div>
