---
target: VibeCut Studio Edit
total_score: 17
max_score: 40
na_heuristics: 
p0_count: 1
p1_count: 4
target_identity: "file:/Users/happynghia/Public/Project/Code/drop_eval/vibecut-studio/static/studio/edit/index.js"
target_fingerprint: "sha256:515bc49ae166ff3b3ffa55b63f406612d37d35b55f7a39c223512004ba9e68be"
target_path: /Users/happynghia/Public/Project/Code/drop_eval/vibecut-studio/static/studio/edit/index.js
timestamp: 2026-11-03T05-54-59Z
slug: static-studio-edit-index-js
---
# VibeCut Studio Edit — Impeccable critique

Method: dual-agent (A: general design review · B: detector/browser evidence).

Design specificity: 5/10. The moment board and transcript vocabulary are product-specific; the surrounding four-tab inspector, preset-heavy panels and eight-lane timeline are category-generic NLE scaffolding.

Heuristic score: 17/40 (Acceptable, lower band).

Priority issues:
- P0 tool panels clipped; inspector content unreachable. Fixed in this pass by making the wrapper a flex pass-through and the body a scroller.
- P1 primary-button contrast 1.87:1. Fixed by restoring the accent ink colour.
- P1 timeline labels sliced by a 6px bar inside a 15px font. Fixed with explicit bar font/inset.
- P1 transcript inert. Fixed: transcript rows are buttons and seek the playhead.
- P1 preview only 131×233. Improved to 184×328 by reducing default timeline height; still below target.
- P2 four competing selection/current states; four names for Clean/Caption; Blank/Add scene semantics.
- P3 tiny lane labels and 10–14px targets, especially at 1280×720.

Detector: 2 pulsing-dot findings in `static/studio/studio.css` (working-step and finish skeleton); no Edit-surface findings because rendered JS markup is outside its reach.

Strengths:
- Hook/Scene/Payoff role model and numbered cut order.
- In-frame safe-zone guidance.
- Broad keyboard model.

Personas:
- Alex: no layer inventory, no transcript search, tiny controls.
- Jordan: TextFX jargon, Clean opens with Rights and Quality warnings before cleanup, panel looked broken.
- Sam: 10–14px targets, 8.5px labels, colour-only selection, hidden overflow.

Remaining direction:
1. Reduce preset density; default one method per tool.
2. Enlarge preview and collapse the timeline by default.
3. Unify selection and naming.
4. Enlarge text controls and targets.
