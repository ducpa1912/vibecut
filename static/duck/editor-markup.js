export function storyBannerMarkup({
  esc, icon, title, beatCount, duration, fullId, editOptions = [],
  sceneOptions = [], beats = [],
}) {
  return `<div class="story-banner">
    <span class="chip green">Story edit</span>
    <strong>${esc(title)}</strong>
    <span class="small muted">${beatCount} beats · ${duration}</span>
    <span class="spacer"></span>
    <select id="story-edit-select" title="Switch edit">
      ${fullId ? `<option value="${esc(fullId)}">Full video</option>` : ''}
      ${editOptions.map((edit) => `<option value="${esc(edit.id)}" ${edit.selected ? 'selected' : ''}>${esc(edit.label)}</option>`).join('')}
    </select>
    <button class="btn small" type="button" data-action="story-add-image">${icon('grid', 12)} Image</button>
    <button class="btn small" type="button" data-action="story-add-video">${icon('film', 12)} Video</button>
    <select id="story-scene-select" ${sceneOptions.length ? '' : 'disabled'} title="Scene to add">
      ${sceneOptions.length
        ? sceneOptions.map((scene) => `<option value="${esc(scene.id)}">${esc(scene.label)}</option>`).join('')
        : '<option>All scenes used</option>'}
    </select>
    <button class="btn small" type="button" data-action="story-add-scene" ${sceneOptions.length ? '' : 'disabled'}>${icon('plus', 12)} Scene</button>
    <button class="btn small" type="button" data-action="back-to-full">${icon('arrowLeft', 12)} Full video</button>
  </div>
  <div class="story-beats">
    ${beats.map((beat) => `<span class="story-beat">
      <span class="chip">${esc(beat.chip)}</span>
      <span class="story-beat-name">${esc(beat.name)}</span>
      <span class="small muted">${beat.duration}</span>
      <button class="icon-btn" type="button" data-action="story-move-beat" data-index="${beat.index}" data-delta="-1" title="Move left" ${beat.first ? 'disabled' : ''}>‹</button>
      <button class="icon-btn" type="button" data-action="story-move-beat" data-index="${beat.index}" data-delta="1" title="Move right" ${beat.last ? 'disabled' : ''}>›</button>
      <button class="icon-btn" type="button" data-action="story-remove-beat" data-index="${beat.index}" title="Remove beat" ${beat.single ? 'disabled' : ''}>×</button>
    </span>`).join('')}
  </div>`;
}

export function mediaInspectorMarkup({
  esc, kind, label, duration, start, end, fileUrl, fileName, isImage, index, total,
}) {
  return `<aside class="panel inspector">
    <div class="inspector-head">
      <h2 class="inspector-title">${kind} beat · ${esc(label || 'Inserted')}</h2>
      <p class="inspector-sub">Inserted beat · ${duration} · story ${start} – ${end}</p>
    </div>
    <div class="inspector-body">
      ${isImage
        ? `<img class="beat-thumb" src="${fileUrl}" alt="">`
        : `<video class="beat-thumb" controls preload="metadata" src="${fileUrl}"></video>`}
      <p class="small muted">Inserted beats render at the story resolution and do not read source clean layers. Source speech is not read for this beat.</p>
      <div class="kv"><span>File</span><strong title="${esc(fileName)}">${esc(fileName)}</strong></div>
      <div class="beat-actions">
        <button class="btn small" type="button" data-action="story-move-beat" data-index="${index}" data-delta="-1" ${index === 0 ? 'disabled' : ''}>‹ Move left</button>
        <button class="btn small" type="button" data-action="story-move-beat" data-index="${index}" data-delta="1" ${index === total - 1 ? 'disabled' : ''}>Move right ›</button>
        <button class="btn small" type="button" data-action="story-remove-beat" data-index="${index}" ${total <= 1 ? 'disabled' : ''}>Remove beat</button>
      </div>
    </div>
  </aside>`;
}

export function audioFocusMarkup({
  esc, icon, rows, music, voice, dub, mixing, sounds = [], voicePanel = '',
}) {
  return `<div class="focus-grid audio-focus">
    <div class="focus-card audio-tracks-card">
      <div class="audio-card-head"><h3>Voice & Music tracks</h3><button class="btn small" type="button" data-action="audio-mix-preview">${icon('play', 12)} ${mixing ? 'Stop' : 'Preview mix'}</button></div>
      <p class="small muted">Drag a block edge to trim, drag the middle to move. Each row can audition on its own.</p>
      <div class="audio-focus-list">
        ${rows.length ? rows.map((row) => `<details class="audio-track-card" data-audio-row="${esc(row.id)}" style="--lane-color:${row.color}" ${row.open ? 'open' : ''}>
          <summary>
            <span class="audio-focus-dot"></span>
            <span class="audio-track-name">${esc(row.name || row.kind)}</span>
            <span class="chip">${esc(row.kind)}</span>
            <button class="icon-btn" type="button" data-action="audio-audition" data-track="${esc(row.id)}" title="Audition this row">${icon('play', 12)}</button>
            <button class="icon-btn${row.muted ? ' is-on' : ''}" type="button" data-action="audio-mute" data-track="${esc(row.id)}" title="Mute">M</button>
            <button class="icon-btn${row.solo ? ' is-on' : ''}" type="button" data-action="audio-solo" data-track="${esc(row.id)}" title="Solo">S</button>
            <button class="icon-btn" type="button" data-action="audio-remove" data-track="${esc(row.id)}" title="Remove">${icon('trash', 13)}</button>
          </summary>
          <div class="audio-row-form">
            <label>Start<input type="number" min="0" step="0.05" value="${Number(row.start || 0).toFixed(2)}" data-audio-field="start" data-track="${esc(row.id)}"></label>
            <label>Length<input type="number" min="0.2" step="0.05" value="${Number(row.duration || 0).toFixed(2)}" data-audio-field="duration" data-track="${esc(row.id)}"></label>
            <label>In<input type="number" min="0" step="0.05" value="${Number(row.offset || 0).toFixed(2)}" data-audio-field="offset" data-track="${esc(row.id)}"></label>
            <label>Volume <span class="audio-value">${Number(row.volume ?? 0.25).toFixed(2)}</span><input type="range" min="0" max="1.5" step="0.01" value="${Number(row.volume ?? 0.25)}" data-audio-field="volume" data-track="${esc(row.id)}"></label>
            <label>Fade in<input type="number" min="0" step="0.05" value="${Number(row.fade_in || 0).toFixed(2)}" data-audio-field="fade_in" data-track="${esc(row.id)}"></label>
            <label>Fade out<input type="number" min="0" step="0.05" value="${Number(row.fade_out || 0).toFixed(2)}" data-audio-field="fade_out" data-track="${esc(row.id)}"></label>
          </div>
        </details>`).join('') : '<p class="small muted">No voice, music or sound tracks.</p>'}
      </div>
    </div>
    <div class="focus-card">
      <h3>Original audio</h3>
      <div class="audio-status"><span class="chip">${dub ? 'Muted by dub' : 'Source bed'}</span><span class="small muted">${dub ? 'The dub replaces the source audio.' : 'Voice-over and music sit over it.'}</span></div>
      <p class="small muted">Mute or solo a row and the source bed follows the same rule on render.</p>
    </div>
    <div class="focus-card">
      <h3>Voice & dub</h3>
      <div class="audio-status"><span class="chip ${voice || dub ? 'green' : ''}">${dub ? 'Dub built' : voice ? 'Voice-over' : 'None'}</span><span class="small muted">${voice ? esc(voice.voice || '') : ''}</span></div>
      ${voicePanel}
    </div>
    <div class="focus-card">
      <h3>Music & SFX</h3>
      ${music ? `<div class="kv"><span>${esc(music.name || 'Music')}</span><button class="btn small" data-action="remove-music">Remove</button></div>` : `<button class="btn wide" data-action="add-music">${icon('volume', 14)} Add music</button>`}
      <div class="sfx-list" style="margin-top:10px">
        ${sounds.map((fx) => `<div class="sfx-row"><span class="sfx-kind">sound</span><span class="sfx-name">${esc(fx.name || 'Sound')}</span><button class="icon-btn" data-action="sfx-remove" data-effect="${esc(fx.id)}">${icon('trash', 14)}</button></div>`).join('') || '<p class="small muted">No sound effects yet.</p>'}
      </div>
      <button class="btn wide" data-action="sfx-add" data-kind="sound">${icon('volume', 14)} Add sound effect</button>
    </div>
  </div>`;
}
