# Loop 9 review — revision 1 (Senior PO, 2026-11-12)

**Fault fixed: the Whisper loop rule dropped real speech.** A line said twice, one copy slow, lost
every copy wherever it appeared. The rule now drops only one run of back-to-back copies.

## What the review project's cues measure

| Copy | Start–end (s) | Words | Seconds/word | Gap before |
|---|---:|---:|---:|---:|
| 1 | 90.00–91.86 | 10 | 0.19 | — |
| 2 | 91.86–92.96 | 10 | 0.11 | **0.00 s** |
| 3 | 94.70–118.06 | 10 | **2.34** | **1.74 s** |

What else sets them apart, read from the stored transcript: the pack returned **no**
`no_speech_prob`, `avg_logprob` or `compression_ratio` (all null), so no score-based rule can run
here. Words exist and their confidences are low and erratic (`I'm` 0.17, `a` 0.02, `little` 0.05),
and two words share the same span (`to` and `eat` both 90.92–90.96 s). The one robust fact is
**local**: the copies follow each other, gaps 0 and 1.74 s, and the last covers 23 s.

## The rule

`_whisper_payload` groups *consecutive* segments with the same line key and a gap of at most
`_REPEAT_GAP` (2.0 s — measured 0 and 1.74 here). A group of two or more is dropped only when one
copy is slow (`_REPEAT_SLOW_SECONDS` 8 s and `_REPEAT_SLOW_PER_WORD` 1.2 s per word). The same line
elsewhere in the video is a separate group and stays. No threshold was added beyond the measured
gap and the measured 23 s/10 words.

## Tests (all pass, 170 total)

- (a) `test_the_review_project_loop_is_dropped` — 90.0, 91.86, 94.7 s, one 23 s copy: all three go.
- (b) `test_the_same_line_a_minute_later_keeps_both` — 60 s apart, one slow: both stay.
- (c) `test_a_chorus_at_speaking_pace_keeps_all_three` — three back-to-back, none slow: all stay.
- (d) `test_one_slow_line_is_kept_when_it_is_not_repeated` — a single slow line stays.

## The stored transcript

`prj_e95348a97316` still holds the three made-up cues: they are in `transcript.json` from a run
before this rule. **The founder must run Check again** to apply it. Check also re-runs detection,
so it **can move clean-layer ranges** and the next render is cold for the spans it changes.

## Gates

170 tests, `node --check` clean, app builds. No fill output change, `textfill.VERSION` stays 17.

---

# Loop 9 review — make the code match the rules

Brief: `BRIEF.md`. Base: loop 8 (`7bda48d`), loop 7 rev 2 (`8d1a9c8`).

**Verdict: 6 of 6 acceptance items pass.** The silent local-model fallback is gone, the dead online
settings are gone, a v1 build reaches no provider, no user-facing string names a model, and the
Whisper cue that nobody spoke is dropped by a small tested rule.

Commits: this commit.

## Acceptance

| # | Item | Result | Evidence |
|---|---|---|---|
| 1 | A test for each of the rewrite order, the dead settings and the cloud guard | **pass** | `tests/test_rewrite_rules.py`: basic cleanup when Apple is unavailable; legacy `online_*` keys load and are dropped; every key set, sockets blocked, rewrite and transcription make no call. `test_duckcore.py` covers the settings route. |
| 2 | The grep command and its empty result | **pass** | `grep -rniE "lama\|whisper\|kokoro\|qwen\|nllb\|deepseek\|gemini\|openai\|groq\|deepgram\|ollama" static/duck` → **no output**. Pack and model labels were renamed (`Extra voice pack`, `Speech pack · non-Apple languages`, `Best · accurate`, `Balanced · smaller`, `AI text fill`), and the fill error copy no longer names a file. `test_no_model_name_in_the_ui` holds the line. |
| 3 | Network guard: rewrite and transcription pass with non-local sockets blocked | **pass** | `test_nothing_leaves_the_mac_with_every_key_set`: `GROQ_API_KEY`, `DEEPGRAM_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `DUCK_STT_PROVIDER`, `DUCK_OLLAMA_*` set; `socket.socket.connect` refuses any host but `127.0.0.1`/`localhost`/`::1`; rewrite falls back to basic cleanup and local transcription runs; zero contacts. |
| 4 | No fill output change, no `VERSION` bump | **pass** | Touched copy and messages only; `textfill.VERSION` stays **17**. |
| 5 | Documents state the test count and that loops 7–9 are done | **pass** | `PLAN.md`, `TODO.md`, `PRODUCT.md`, `CLAUDE.md`: **169 tests**, brief loops 7–9 closed, PLAN loops 7–9 still open (model slots, $29 readiness, layout). |
| 6 | `pytest`, `node --check` | **pass** | **169 passed**; JS clean; the app builds. |

## What changed

1. **Rewrite order.** `script.rewrite` no longer tries a local model endpoint: Apple Intelligence
   when the Mac has it, else a plain cleanup. The `qwen3:4b` name and the 120 s HTTP call are
   deleted, and the UI says which engine ran (`Apple Intelligence` / `basic cleanup`).
2. **Dead settings.** `online_enabled` and `online_endpoint` are gone from defaults, the snapshot,
   the PATCH model and the tests. An old `settings.json` that still holds them loads normally and
   drops them on the next save.
3. **Cloud speech.** No auto provider exists; `stt.transcribe` is local only. The guard test proves
   it with every key set.
4. **Model names.** The four `LaMa` strings in Settings, the pack labels, the two STT quality
   labels, the `/api/models` label and the fill error copy are neutral now.
5. **The Whisper cue.** `I'm going to eat a little bit of chicken.` appears three times at
   90–118 s on the review project. Cause: the Whisper pack returns **no** `no_speech_prob`,
   `avg_logprob` or `compression_ratio`, so the existing score filters could never run, and the
   phrase is not in the known-hallucination list. One copy covers **23.36 s for 10 words**
   (2.3 s a word). Rule: a line repeated at least twice, where one copy covers ≥ 8 s at ≥ 1.2 s a
   word, is a loop over music or room noise and is dropped. Tested: the three cues go, a single
   slow line stays. The existing transcript is unchanged; the next Check applies it.

## What got worse

- The review project still holds the three cues until Check runs again. Not re-run: it also
  re-runs detection and would change layer ranges, which this loop must not do (no fill output
  change).
- Nothing else: no fill output change, no `VERSION` bump, no cold render.

## Not tested

- The renamed labels and the rewrite engine label in the built app's Settings/Script screens; the
  JS is syntax-checked and the app builds, the screens were not read.
- The Whisper rule on a second language or a real long pause in speech; only synthetic payloads and
  the review project's data.
- Cloud providers are still compiled in; the test proves the v1 path does not reach them, not that
  the code is absent (by design: it returns after v1).
