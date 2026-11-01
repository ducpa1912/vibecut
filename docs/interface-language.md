# Interface language

VibeCut Classic and Voice Room ship with **English** and **Vietnamese** interface
copy.

- Choose the language from the **EN / Tiếng Việt** selector in the top bar.
- The choice is stored per browser in `localStorage` (`vibecut.ui_lang`).
- `?lang=vi` opens a page in Vietnamese once and remembers it.
- The Classic page and Voice Room load `static/classic/i18n.js`; dynamic
  strings rendered by the app are translated as they appear.
- Untranslated strings fall back to English, so new features never break the
  page.

The translator is intentionally a small DOM dictionary rather than a build-time
i18n framework: Classic and Voice Room render most copy from JavaScript, and a
live translator covers both static and dynamic text without duplicating every
template.
