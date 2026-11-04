# Classic ↔ Studio feature matrix

Date: 2026-11-04
Decision context: Classic is a **second supported product**, Studio is the
integration/product lane, monorepo with separate apps and a pinned `core/`
profile contract.

Branches compared: `studio` at `78e960a` and `classic` at `6c6e3ec`.
This matrix is about **user-facing capability**, not raw branch divergence.

## Summary

| Group | Classic-only? | Studio state | Port decision |
|---|---|---|---|
| Vietnamese interface and glossary | Yes | English-only Studio UI | **Port (high value)** |
| Machine capability summary | Yes | Engine rows exist; no one-line “On-device / Cloud / Mixed AI” summary | **Ported** |
| Paid-action cost/data notices | Yes | No equivalent trust surface | **Ported** |
| Stale render baseline marker | Yes | Trim/Edit stale exists; artifact-vs-edit baseline is not surfaced | **Ported** |
| Text shape limit warning | Classic limits text to 9:16/4:5 | Studio renders text on every shape; no shape warning is valid | **Do not port the false warning; warn at the real 32-slot cap** |
| Preview vs render source labels | Yes | Studio preview is frame-render based; less ambiguity | Skip |
| Clean “removes/keeps” explanation | Yes | Studio Clean has reasons and blocked states | Skip |
| Audio mode naming and BGM choices | Classic-specific labels | Studio has Original / Voice-Over / Dub + music hub | Skip; Studio owns new wording |
| AI music preview lock | Classic concurrency guard | Not confirmed in Studio | **Port if missing** |
| C0–C4 frame / boxes / scan | Classic port of Studio patterns | Studio is the source | No port |
| AI fill core | Classic ported shared backend | Studio source | No port |
| Cobalt removal / XHS limits | Classic product decision | Studio already uses yt-dlp / no Cobalt UI | No port |
| Signed-commit / release scripts | Lane tooling | Not product | No port |

## Detailed matrix

| # | Capability | Classic evidence | Studio evidence | User value | Cost/risk | Recommendation |
|---|---|---|---|---|---|---|
| 1 | Vietnamese UI, curated glossary, dynamic-copy safety | `static/classic/i18n.js`, `docs/shared/vi-glossary.md`; `8186e2a`, `0e275e7`, `ba31215` | No Studio i18n tree; Studio strings are inline English | High for Vietnamese creators | Medium: extract keys without changing Studio layout | **Port high-value subset** |
| 2 | Capability snapshot: On-device AI / Cloud AI / Mixed AI | `483c882`; Setup capability row | Setup lists engines and install state, but no single capability verdict | Prevents false “local only” expectations | Low: read existing health/engine data | **Ported** — `trust.js` + Setup |
| 3 | Cost + data notice before paid actions | `f9f327f`, `5e54310`, `8887174`; `static/classic/trust.js` | No equivalent cross-step trust surface | High: spending and privacy trust | Medium: copy + data source + tests | **Ported** — Setup, Audio, Finish |
| 4 | Mark renders that no longer match the current edit | `32e573a`; render baseline in job | Finish handles trim/Edit stale, not “render older than this cut” | High: prevents publishing stale output | Medium: compare render spec/baseline | **Ported** — `artifactIsStale` |
| 5 | Text shape limit warning before dropping layers | `ef35c51`; Classic only renders text on 9:16/4:5 | Studio renders text on all five shapes; `edits.py` caps graphics at 32 | Prevents surprise at the real cap | Low | **Ported as the real 32-slot cap warning** |
| 6 | Separate preview buttons from what the render uses | `9d9ed87`; sample/render distinction | Studio preview is the actual frame route; render uses same compile | Low now | Low | Skip |
| 7 | Clean explanation: exactly what is removed/kept | `1652c92`; trust Copy | Studio Clean has blocked reasons, watermark/screen UI states, Box/timing detail | Covered | Low | Skip |
| 8 | Audio modes: New voice-over, Dub voice, New voice + music, Use my BGM | Classic pass docs; `19d0d55` | Studio has Original / Voice-Over / Dub and Library/Upload/GenAI music | Both valid product models | High to merge two mental models | Skip; keep Studio model |
| 9 | One preview lock per file / AI music preview | `944be8d` | Not confirmed | Avoids double preview race | Low | **Check, then port if missing** |
| 10 | Empty text/effects payload renders on any shape | `1afa403` | Shared backend path; parity not proven | Prevents blank render | Low | **Check shared tests** |
| 11 | C0–C4 frame, boxes, scan, AI fill | `bab368d`, `fb7c9d8`, `6c6e3ec` | Studio source for these patterns | Already ahead | High duplication | No port |
| 12 | Cobalt removal and XHS limits | `8186e2a` | Studio uses yt-dlp; no Cobalt UI | Covered | Low | No port |
| 13 | Signed commits, beta tag, lane scripts | Classic lane tooling | Studio ship/main flow | Operational | Not user-facing | No port |

## Approved port set

1. Capability summary in Studio Setup.
2. Paid-action cost/data notices shared across Setup, Edit audio and Finish.
3. Stale-render baseline marker in Finish.
4. Real 32-slot text/effect cap warning in Edit. Classic's 9:16/4:5 limit does not apply to Studio.

Deferred: Vietnamese interface, AI-music preview lock.

## Explicitly not ported

- Classic’s page layout, top bar and lane navigation.
- Classic audio-mode wording; Studio’s Original/Voice-Over/Dub model stays.
- Classic Clean trust copy; Studio’s Clean states already exceed it.
- Classic release/signing scripts.

## Evidence commands

```bash
git log --oneline studio..classic
git log --oneline classic..studio
git show --stat <commit>
```
