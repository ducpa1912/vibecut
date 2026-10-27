/**
 * Studio — Edit placeholder.
 * One editor per story; the base editor lands in the next wave.
 */

const LAYERS = [
  ["Clean", "Hide old text with a plate, a blur or a tighter crop."],
  ["Text", "Hook card, title, lower third and end card."],
  ["Captions", "Word-timed captions in the style you pick."],
  ["Effects", "Punch-in, push and shake, snapped to the beat."],
  ["Color", "A preset, then small exposure and warmth changes."],
  ["Audio", "Original sound, voice-over, music and ducking."],
];

export function mount(root, ctx) {
  root.innerHTML = `
    <section class="st-panel" aria-labelledby="st-edit-title">
      <header class="st-panel-head">
        <p class="st-eyebrow">Step 4 · Edit</p>
        <h1 id="st-edit-title">Shape each story</h1>
        <p class="st-lede">Every story gets one editor and one saved cut. Layers stay in the same order, so preview and export always match.</p>
      </header>
      <div class="st-placeholder" role="note">
        <div class="st-placeholder-mark" aria-hidden="true">04</div>
        <div class="st-placeholder-copy">
          <h2>Edit is coming next</h2>
          <p>The base editor opens after Stories. Your story picks are ready for it.</p>
        </div>
      </div>
      <ul class="st-feature-list st-feature-list-two">
        ${LAYERS.map(([title, copy]) => `<li><strong>${title}</strong><span>${copy}</span></li>`).join("")}
      </ul>
      <div class="st-actions">
        <button id="st-edit-stories" class="st-btn st-btn-primary" type="button">Open Stories</button>
      </div>
    </section>
  `;
  root.querySelector("#st-edit-stories")?.addEventListener("click", () => ctx.go("stories"));
}
