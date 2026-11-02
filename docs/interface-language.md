# Interface language

VibeCut Classic and Voice Room ship with **English** and **Vietnamese** interface
copy.

- Choose the language from the **EN / VI** switch in the top bar.
- The choice is stored per browser in `localStorage` (`vibecut.ui_lang`).
- `?lang=vi` opens a page in Vietnamese once and remembers it. Switching back
  to English removes the `lang` query parameter, so the next reload is English.
- The Classic page and Voice Room load `static/classic/i18n.js`; dynamic
  strings rendered by the app are translated as they appear in Vietnamese.
- English is the source language. The live translator is idle in English, so
  new dynamic copy is never turned into Vietnamese by accident.
- Untranslated strings fall back to English, so new features never break the
  page.

The translator is intentionally a small DOM dictionary rather than a build-time
i18n framework: Classic and Voice Room render most copy from JavaScript, and a
live translator covers both static and dynamic text without duplicating every
template.
