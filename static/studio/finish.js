/**
 * Studio — Finish placeholder.
 * Render, versions, publish kit and review links land in the Finish wave.
 */

const STEPS = [
  ["Render", "One story or all of them, in 9:16 and 4:5."],
  ["Compare", "Versions stay side by side. Nothing is overwritten."],
  ["Publish kit", "Titles, description, hashtags, covers and the cut itself."],
  ["Review link", "A private link for one person, bound to that exact cut."],
  ["Exports", "The video, captions and an edit list for other tools."],
];

export function mount(root, ctx) {
  root.innerHTML = `
    <section class="st-panel" aria-labelledby="st-finish-title">
      <header class="st-panel-head">
        <p class="st-eyebrow">Step 5 · Finish</p>
        <h1 id="st-finish-title">Render and share</h1>
        <p class="st-lede">Send finished stories to a folder, or pass a private review link. Every version keeps its own record.</p>
      </header>
      <div class="st-placeholder" role="note">
        <div class="st-placeholder-mark" aria-hidden="true">05</div>
        <div class="st-placeholder-copy">
          <h2>Finish is coming next</h2>
          <p>Render from Stories for now. This screen adds versions, covers and review links.</p>
        </div>
      </div>
      <ul class="st-feature-list">
        ${STEPS.map(([title, copy]) => `<li><strong>${title}</strong><span>${copy}</span></li>`).join("")}
      </ul>
      <div class="st-actions">
        <button id="st-finish-stories" class="st-btn st-btn-primary" type="button">Open Stories</button>
      </div>
    </section>
  `;
  root.querySelector("#st-finish-stories")?.addEventListener("click", () => ctx.go("stories"));
}
