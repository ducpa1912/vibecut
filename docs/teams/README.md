# DuckSuite UI revamp — one team, three block sessions

One team. Three sequential sessions. Each session owns one block. A finished block is reviewed by the product owner before the next block starts. Any block can be reopened later without restarting the whole programme.

## Current agent roles

The block sessions below are the historical record. Coding work now runs through five agents defined
in `.claude/agents/` and in `AGENTS.md`:

| Role | Owns | Gate |
|---|---|---|
| `product-owner` | Brief, acceptance, screen review, sign-off | Final gate before commit |
| `creator` | Taste and flow as a real creator | Advisory, notes required |
| `engineer` | Code, tests, invariants | Tests and syntax pass |
| `tester` | Reproduction, failing test, build check | A fail blocks sign-off |
| `researcher` | API availability, licences, sizes, costs | Facts cited |

Loop: brief → build + tests → creator use → tester pass/fail → sign-off → one commit with `MEMORY.md`,
`TODO.md` and the report row. The user is the final authority.

## Sessions

| Session | Block | Screens | Review record |
|---|---|---|---|
| **Team — Welcome & Check** | Welcome, Check | Upload, projects, queue, finished renders, scene-first handoff | [team-1-welcome-check](team-1-welcome-check/review-02.md) |
| **Team — Edit & Clean Focus** | Edit, Clean Focus | Proof Rows, transcript, captions, voice, fine trim, clean proof, layers | [team-2-edit-clean](team-2-edit-clean/review-02.md) |
| **Team — Preview & Render** | Preview, Render | Before/after player, automatic clean pass, queue, output | [team-3-preview-render](team-3-preview-render/review-02.md) |

Settings remains a native sheet, not a block. No shell step.

## Flow

```text
Welcome → Check → Edit ⇄ Clean Focus → Preview → Render → Welcome
```

- Welcome is the entry.
- Check cuts scenes first, then opens Editor while transcript, text detection, and stories continue.
- Clean Focus is the Editor frame with only clean tools.
- Preview starts clean scene by scene. The blur is a processing placeholder, never a render fallback.
- Render returns finished output to Welcome.

## Review loop

Each block runs:

1. **Design loop** — UX/UI proposes; product owner amends and approves.
2. **Dev loop** — engineering builds; product owner enforces fixes.
3. **Testing loop** — QA writes unit/UAT and hunts bugs; product owner enforces depth.

Every review is recorded in Markdown with the rendered screen, verdict, good-to-go list, revision list, bug list, and failed items.

## Visual contract

Daylight Story Desk:

- warm paper `#F7F4EE`, raised `#FFFFFF`, ink `#1C1B19`, muted `#5F5B54`, line `#E4DED3`;
- amber `#A9540C` / `#F0A45C`, success `#2F7D5B`, danger `#B23A2E`, video `#0E0E10`;
- SF Pro UI, SF Mono timecode, no serif;
- flat surfaces, 1px hairlines, one amber primary action;
- no newsroom, parchment, darkroom, glass, gradients, mascot illustration, extra modes.

## Clean quality

Separate clean-quality work is tracked in [clean-quality/loop-01.md](clean-quality/loop-01.md) and [clean-quality/loop-02-plan.md](clean-quality/loop-02-plan.md). Baseline complete: proof/render mismatch reproduced; render still has a 1.8 s dark pill; 1 fps is a regression; 8 fps is clamped and fragments titles. Loop 2 implementation landed: shared proof/render frame path, glyph/bright-text masks, per-sample boxes, fill_keys, range edges, and 24 tests. Gate is partial: scene 01 1.8 s and scene 07 25.875 s pass; scene 01 3.5 s still fails. Loop 3 adds shared blur parity, an edge-text OCR pass, and a raised scan cap; the edge pass recovers the missing word but the fill ghosts earlier title frames, so it is disabled by default. See [clean-quality/loop-03.md](clean-quality/loop-03.md).

## User test

First-time solo-creator test: [user-test-01.md](user-test-01.md). Verdict: FAIL. Proof/render parity, Check handoff timing, captions, fine trim, hidden clean layers, and proof invalidation are the blockers.

## Build report

See [BUILD-REPORT.md](BUILD-REPORT.md).

## Build notes

- Frontend: `static/duck/index.html`, `static/duck/app.css`, `static/duck/app.js`.
- Local core: FastAPI; scene cut is published before transcript/OCR so Editor can open early.
- Frame and clean-proof endpoints are cached per edit version.
- Dev server: `scripts/serve-duck.sh`.
- Screenshots for review: 1440 × 1000, full page, via local Chrome.

## Current integration state

- Six screens built and connected to the local core.
- Welcome, Check, Edit, Clean Focus, Preview, and Render reviewed.
- Known launch risk: LaMa proof quality on very large stylized text; scene 07 is a clean verified example, scene 01 shows an artifact. The UI exposes Fill / Blur / Off and does not hide the result.
