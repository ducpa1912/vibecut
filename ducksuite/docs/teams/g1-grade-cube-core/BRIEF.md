# G1 core · One grade, one colour cube (REQ-20261126-01)

Owner: **Codex**. Folder `drop_eval/ducksuite-codex`, branch `cx/g1-grade-cube-core`.
Founder, 2026-11-26: "Start G1 core half". Plan: `docs/plans/2026-11-26-editroom-adoption.md` (G1).
This is the **core half only**: no `static/duck/app.js` or `app.css`. OpenCode owns `app.js`
for P-E right now. The preview half (WebGL in the page) is a second loop, after P-E merges.

## Why
Preview and render disagree today:
- **Preview:** `gradeFilter` (`app.js` about line 1675) uses CSS filters. Exposure +50 gives
  brightness ×1.25. Temperature is `sepia` or `hue-rotate`.
- **Render:** `render.py` (about lines 246–260) uses FFmpeg `exposure`, `eq` and `colorbalance`.
  Exposure +50 gives +1 stop, ×2.0.

Editroom (MIT, © 2026 Wonder Assembly LLC, `github.com/robbietilton/Editroom` at `e0cbfd2`)
avoids this by baking the whole grade into one colour cube. The viewer, the thumbnails and the
export all use that same cube.

## Files you own
- `duckcore/grade.py` (new): the grade model, the recipe maths, the looks, `.cube` read and write, and the bake.
- `duckcore/render.py`: only the grade part of the video filter, which becomes `lut3d`.
- `duckcore/edits.py`: only `GRADE_KEYS` and the grade cleaning (about line 635), for `tint`,
  `look` and `look_strength`.
- `duckcore/main.py`: new grade routes only (below).
- `Licenses/Editroom-MIT.txt` (new), with Editroom's copyright and permission notice.
- `tests/test_grade_cube.py` (new), `docs/teams/g1-grade-cube-core/review.md`.

## Done looks like
1. **Model.** The edit's grade keeps today's slider range of −100 to 100 for exposure,
   contrast, saturation and temperature. It adds:
   - `tint`, −100 to 100;
   - `look`: a built-in look name, a user LUT id, or none;
   - `look_strength`: 0 to 100, default 100.

   Old saved edits load unchanged. Write the mapping from our range to the maths in the review,
   for example exposure ±100 to ±2 stops, which keeps today's render meaning.
2. **Maths.** Port Editroom's `GradeRecipe.apply` order:
   - exposure, then temperature and tint;
   - then the tonal wheels (stored as zero for now: the wheels come later);
   - then contrast, fade, and saturation.

   Port the 8 built-in looks with their names: Warm film, Golden hour, Film print, Teal and
   orange, Pastel, Bleach bypass, Mono, Cool night. Include the `LookMath` functions. Keep the
   Editroom MIT notice in `Licenses/Editroom-MIT.txt` and say in the file header which parts
   came from it. Look strength mixes the look's output with its input, then the adjustments are
   applied on top. Work in NumPy, vectorised over the cube.
3. **Bake.** `grade.bake(grade, data_root)` writes one 33³ `.cube` (Adobe format, the
   `LUT_3D_SIZE` header, red changing fastest). It is cached by a hash of the grade, plus the
   user LUT file's hash when there is one. A neutral grade bakes nothing.
4. **Render.** Render applies the cube with `lut3d=file=<path>:interp=tetrahedral` where the
   FFmpeg grade filters are today. `exposure`, `eq` and `colorbalance` are removed.
   - Our LGPL FFmpeg has `lut3d`; I checked with `ffmpeg -filters`.
   - The render cache key includes the cube hash. Say in the review that the **next render of a
     graded edit is cold**.
   - Fill output doesn't change, so no `textfill.VERSION` bump.
   - Blur and sharpen keep their order relative to the grade.
5. **User LUTs.** `POST` a local `.cube` path, the same way the translation folder is chosen.
   - The core checks it:
     - 3D only (refuse a 1D LUT, with a plain message);
     - `LUT_3D_SIZE` from 2 to 65;
     - every value finite;
     - `DOMAIN_MIN` and `DOMAIN_MAX` read and honoured, or refused if they aren't 0..1;
     - file size at most 20 MB.
   - It copies the file into `<data root>/luts/` under an id, and lists the LUTs with their file
     names. Nothing is downloaded and none is shipped.
6. **Routes for the preview half.**
   - The baked cube for an edit's grade, as JSON (size plus a flat float32 array, base64), so
     the page can upload it to WebGL later.
   - A graded still frame at a given time, made by the core with the same cube. That is the
     preview's fallback when WebGL is missing.
   - The list of looks and the user LUTs.
7. **Proof.** Make a synthetic colour chart PNG: an RGB ramp grid you generate, not footage.
   - Run 4 grades through `grade.py` in NumPy and through an FFmpeg `lut3d` render: neutral,
     exposure +50, temperature −60 with tint +30, and Teal and orange at 70%. Every patch must
     match within 2/255. Put the table in the review.
   - Also record how far today's render moves for exposure +50 and temperature +50, measured on
     the chart. That's the visible change a creator will see.
8. **Tests.** `tests/test_grade_cube.py` covers:
   - old edit compatibility;
   - the neutral grade baking nothing;
   - cube file format round-trip;
   - LUT refusals: 1D, wrong size, NaN, too large;
   - look strength at 0 equal to no look;
   - the render filter containing `lut3d`, and no longer `eq` or `colorbalance`;
   - the cache key changing with the grade.

   The full suite and `node --check static/duck/app.js` pass. **Do not open the app.**

## Notes
- Base: `ducksuite` at `e971c20` or later.
- Don't touch `static/duck/`. List in the review what the preview half will need: the routes, the
  JSON shape, and the WebGL fallback rule.
- Commit on `cx/g1-grade-cube-core` with `git -c commit.gpgsign=false commit`. Don't push.
  Don't edit `MEMORY.md`, `TODO.md`, `PLAN.md` or `PRODUCT.md`.
- If you check anything by hand, use port 8831 and `build/scratch-root` only. No founder media.
