# Short-cut rewrite prompt

The rewrite has one job: turn the full source voice over into a short cut that
still sounds like the same video. It is not a line-by-line translation.

## Inputs

Before the model writes, VibeCut builds:

- **FULL VOICE SCRIPT** — the complete transcript, translated once into the
  target language. OpenCode reads up to 6,000 characters; local models use the
  story brief plus BM25-retrieved lines.
- **VIDEO AESTHETIC** — moods, visual tags, subject type, pacing and beat roles
  derived from the selected scenes:
  ```json
  {
    "moods": ["calm", "ambient", "soft", "warm"],
    "visual_tags": ["subject", "motion", "text"],
    "subject": "people",
    "pace": "measured",
    "avg_beat_seconds": 3.0,
    "roles": ["hook", "beat", "beat", "payoff"]
  }
  ```
- **STORY BRIEF** — topic, audience, promise, proof, tone, hook/payoff ideas
  (when available).
- **BEAT SLOTS** — one row per selected beat:
  ```json
  {"beat": 0, "role": "hook", "seconds": 3.0,
   "max_chars": 40, "max_words": 8,
   "source_line": "完整源句", "literal": "literal translation"}
  ```

## Prompt rules

The generated prompt currently says:

1. Write **one coherent voice over**, not separate captions.
2. Read the full voice script and visual aesthetic first.
3. Exactly N lines, in beat order.
4. Every line is a **complete grammatical sentence** with terminal punctuation.
5. Stay within both `max_chars` and `max_words`. **Condense or rephrase; never
   truncate, never end on a conjunction/preposition/article, never output
   ellipses or a fragment.**
6. Structured calls keep `reasoning_effort: low` but send
   `thinking: {"type": "disabled"}`. On this model, hidden chain-of-thought
   could consume the entire token budget and return empty content. Disabling it
   keeps the low-effort setting without the empty replies.
7. Use pronouns and natural transitions so the cut reads as one story.
8. Keep the hook promise and payoff resolution; keep products, numbers and
   claims; invent nothing.
9. Write native target-language phrasing, not word-for-word translation.

## Two-pass repair

Small/fast models often write a good sentence that is too long. Truncating it
was the source of lines like “...and scattered.” or “...such a big.”

Now:

1. First pass writes the N lines.
2. Any line over `1.15 ×` its slot, ending on a bad function word, or ending in
   an ellipsis is sent to a **condense pass** with the full script, aesthetic,
   and exact char/word budgets.
3. The condense pass must return complete sentences. Only if that pass fails does
   VibeCut keep a clause-level fallback, and it still adds terminal punctuation.

Results are cached under `REWRITE_VERSION`; changing the prompt invalidates old
fragments.

## Example

Source line: `谁懂啊，终于把宫崎骏的动漫世界搬进了自己的乡下小院。`

Instead of a truncated caption, a 3-second hook becomes:

> Miyazaki's world now lives in my yard.

Complete, in the target language, within the slot, and still tied to the
original story.
