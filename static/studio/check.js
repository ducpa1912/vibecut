/**
 * Studio — Check placeholder.
 * The live screen lands with the Check backend; this keeps the step visible.
 */

const ITEMS = [
  ["Text on screen", "Baked-in captions, titles, handles and platform marks."],
  ["Speech", "Where people talk, and how much of the video carries words."],
  ["Music", "Whether the source already has a bed under the speech."],
  ["Faces", "Who is on screen, and where the crop should stay."],
  ["Picture quality", "Size, motion and compression before a cut is chosen."],
];

export function mount(root, ctx) {
  root.innerHTML = `
    <section class="st-panel" aria-labelledby="st-check-title">
      <header class="st-panel-head">
        <p class="st-eyebrow">Step 2 · Check</p>
        <h1 id="st-check-title">See what the footage needs</h1>
        <p class="st-lede">Check reads the source before any story is cut. It finds old text, speech, music, faces and picture problems, then suggests the smallest fix.</p>
      </header>
      <div class="st-placeholder" role="note">
        <div class="st-placeholder-mark" aria-hidden="true">02</div>
        <div class="st-placeholder-copy">
          <h2>Check is coming next</h2>
          <p>Import and Stories work now. This screen opens when the source read is ready.</p>
        </div>
      </div>
      <ul class="st-feature-list">
        ${ITEMS.map(([title, copy]) => `<li><strong>${title}</strong><span>${copy}</span></li>`).join("")}
      </ul>
      <div class="st-actions">
        <button id="st-check-import" class="st-btn st-btn-ghost" type="button">Back to Import</button>
        <button id="st-check-stories" class="st-btn st-btn-primary" type="button">Open Stories</button>
      </div>
    </section>
  `;
  const back = root.querySelector("#st-check-import");
  const next = root.querySelector("#st-check-stories");
  back?.addEventListener("click", () => ctx.go("import"));
  next?.addEventListener("click", () => ctx.go("stories"));
}
