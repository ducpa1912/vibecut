# UI/UX internal review 01

Date: 2026-11-08
Reviewers: product owner, engineer, tester.
Build: packaged Xcode app, 1280 × 800 and 1440 × 900.
Scope: compare the six shipped screens with the Phase 1 plan, the three team reviews, and user-test-02.

## Verdict

**Pass for the v1 six-screen flow.** Four UI defects fixed in this pass. The remaining differences are deliberate v1 scope cuts or missing secondary tools, not broken flows.

## Fixed in this pass

| Screen | Issue | Fix |
|---|---|---|
| Welcome | Latest render repeated as the first Recent row; when it was the only render, Recent still said “None” | Latest render excluded from Recent; empty Recent block removed |
| Check / Clean / Preview | Scene strips scrolled but had no arrow controls; reviews asked twice | ‹ › buttons scroll each strip |
| Render | `1 JOBS` | `1 job` |
| Settings | “Online jobs” endpoint implied cloud render in a local-only v1 | Removed from Settings |
| Clean / Settings | User-visible model name “LaMa” | “AI fill” |
| Clean Focus | Top step read “Clean focus”, making a fifth mode | Step stays “Edit”; Clean Focus is the mode |
| Settings | Leftover online-jobs endpoint implied cloud render | Removed |
| Static shell | Unreferenced `duck.js` / `duck.css` from an earlier shell | Deleted |

## Plan comparison

| Plan item | Current | Verdict |
|---|---|---|
| Mac App Store, $29, no account | Bundled, offline, no account | Ready except signing |
| Six-screen flow | Welcome, Check, Edit, Clean Focus, Preview, Render | Pass |
| Scene-first Check handoff | Scenes open Edit with running banner; old edit cleared | Pass |
| Proof before render | Render disabled until every scene has no text, Off, or a proof | Pass |
| AI fill default, Blur explicit, Off | Fill / Blur / Off; no silent fallback | Pass |
| No layer cap | Show all layers and cues | Pass |
| One proof per scene | v10 proof; parity MAD 2.30 | Pass |
| Scene strip overflow | Arrow controls | Pass |
| Queue archive | Clear finished | Pass |
| 1080p, 24/30 fps | Enforced in Render settings | Pass |
| Fine trim | In/Out fields write the clip | Pass, numeric not drag |
| Captions | Editable, burn/SRT, max 4 s, no duplicates | Pass |
| Manual clean box | Absent | Open, P2 |
| Per-line voice preview | Only generated voice preview | Open, P2 |
| Project rename/delete | Not exposed | Open, P2 |
| Multi-aspect export | Source aspect only | Deliberate v1 cut |
| Dub | Absent | Deliberate v1 cut |
| Cloud render | Absent; Settings no longer implies it | Deliberate v1 cut |
| Cover JPG export | Absent | Deliberate v1 cut |
| Model pack manager | Bundled models only | Deliberate v1 cut |

## Remaining UX risks

1. **Fine trim is below the fold at 1280×800.** The page scrolls; no label is clipped. A taller window is the intended review size.
2. **Compare still hides the left half of the After frame.** After is the default; Compare is a deliberate wipe.
3. **Proof generation is serial.** A 12-scene preview takes minutes on the local model.
4. **The demo screenshot footage is internal.** Replace with cleared 16:9 footage before submission.

## Acceptance after this pass

- Arrow buttons scroll Check, Clean, and Preview strips.
- One done render appears once, in Latest Render.
- Render queue says `1 job`.
- Settings no longer offers an online endpoint.
- No “LaMa” string in the UI.
- 41 tests pass.
- Xcode build and unsigned archive pass.

## Recommendation

Ship the six-screen flow. Do not add dub, cloud, multi-aspect, or model packs to v1. Add the manual box tool and per-line voice preview only if the review timeline allows a new feature pass; they are not broken, they are absent.
