# Vietnamese UI glossary

Vietnamese is a **UI/UX language**, not a forced translation of every English
string. The interface keeps product names, acronyms and short English terms
when that is clearer or more natural.

## Principles

1. Translate the **task and the meaning**, not every word.
2. Keep user content in its original language: job titles, file names,
   transcript, OCR text, captions, comments.
3. Keep provider and model names unchanged.
4. Keep acronyms and units unchanged.
5. If a short English term is the normal term in Vietnamese video editing, keep
   it.
6. A missing translation falls back to English; it never breaks the page.
7. English is the source language. The translator is idle in English.

## Keep in English

- Product names: `VibeCut`, `Studio`, `Creator`. `Voice Room` may be translated
  as `Phòng giọng nói` in navigation, but stays `Voice Room` in configuration
  and provider names.
- AI and API terms: `AI`, `TTS`, `STT`, `API`, `URL`, `JSON`, `HTTP`
- Providers and models: `OpenCode`, `OpenRouter`, `ElevenLabs`, `MiniMax`,
  `OpenAI`, `Groq`, `Deepgram`, `Whisper`, `Apple Vision`, `yt-dlp`, `XHS`,
  `xhs_get`, `FFmpeg`, `Signalsmith`
- Units and formats: `fps`, `dB`, `px`, `s`, `ms`, `×`, `9:16`, `4:5`, `1:1`,
  `16:9`, `16:10`, `1080×1920`
- Common editor terms when clearer: `Render`, `SFX`. `Clean`, `Draft` and
  `BGM` are translated in navigation labels but stay unchanged in code and
  provider names.
- Short UI labels where Vietnamese would be longer or awkward.

## Translate

- Navigation and tasks: `Setup` → `Cài đặt`, `Save` → `Lưu`, `Cancel` → `Hủy`,
  `Delete` → `Xóa`, `Download` → `Tải xuống`.
- Explanations and warnings: privacy, cost, rights, missing models, failed
  renders.
- Empty states and errors.
- Voice-fit and platform-capability explanations.

## Do not translate

- User job titles, file names, transcript lines, OCR text, caption text.
- Model output, provider errors, raw API messages.
- `data-i18n-skip` regions.
- Any string that is not explicitly marked for translation.

## Implementation

- Static UI: `data-i18n="key"` on the element.
- Dynamic UI: `t("key", {count})`.
- No global DOM `MutationObserver`.
- No substring translation.
- No automatic translation of new English copy.
- The EN/VI switch changes only curated UI copy.

## Review checklist

- English mode has no Vietnamese leakage.
- Vietnamese mode has no forced English sentence where a natural Vietnamese
  sentence exists.
- Acronyms and provider names are unchanged.
- User content is unchanged.
- The same screen does not mix languages in a single sentence unless the term
  is intentionally kept.
