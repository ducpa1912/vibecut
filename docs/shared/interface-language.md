# Interface language

VibeCut Classic and Voice Room ship with **English** and **Vietnamese**
interface copy.

- Choose the language from the **EN / VI** switch in the top bar.
- The choice is stored per browser in `localStorage` (`vibecut.ui_lang`).
- `?lang=vi` opens a page in Vietnamese once and remembers it. Switching back
  to English removes the `lang` query parameter.
- English is the source language. The live translator is idle in English.
- Vietnamese is curated UI/UX copy, not a forced translation of every string.
  Product names, acronyms and short English terms stay English when that is the
  better UX. See [the Vietnamese glossary](vi-glossary.md).

The translator only touches explicit UI copy. User content, job titles, file
names, transcript lines, OCR text and provider/model names are never
translated.

The old whole-DOM dictionary is being replaced by explicit keys and a `t()`
helper so new dynamic English copy is not translated by accident.
