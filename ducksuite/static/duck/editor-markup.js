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
  total = 0, sourceMuted = false, fmtTime = () => '0:00', ticks = [],
}) {
  const span = Math.max(0.1, Number(total) || 0);
  const pct = (value) => Math.max(0, Math.min(100, (Number(value) || 0) / span * 100));
  const short = (value) => {
    const seconds = Math.max(0, Number(value) || 0);
    return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
  };
  const audible = rows.filter((row) => !row.muted);
  const soloActive = rows.some((row) => row.solo);
  const dubRow = audible.some((row) => row.kind === 'dub');
  const voiceOnlyRow = audible.some((row) => row.kind === 'voice' && row.mode === 'voice_only');
  const voices = audible.filter((row) => row.kind === 'voice' || row.kind === 'dub');
  const musicRow = rows.find((row) => row.kind === 'music');
  const level = (value, fallback) => `${Math.round((Number(value ?? fallback) || 0) * 100)}%`;
  let bed;
  if (sourceMuted) bed = { text: 'Muted here', tone: 'is-off', note: 'You muted the source bed in Audio Focus.' };
  else if (soloActive) bed = { text: 'Removed · 0%', tone: 'is-off', note: 'A row is soloed, so the source bed is dropped on render.' };
  else if (dubRow) bed = { text: 'Muted by dub', tone: 'is-off', note: 'The dub replaces the source audio.' };
  else if (voiceOnlyRow) bed = { text: 'Removed · 0%', tone: 'is-off', note: 'A voice row is set to voice only, so the source is dropped.' };
  else if (voices.length) bed = { text: '22% under voice', tone: 'is-duck', note: 'The source drops to 22% whenever a voice or dub row is present.' };
  else bed = { text: '100%', tone: '', note: 'No voice row, so the source plays at full level.' };
  return `<div class="focus-grid audio-focus">
    <div class="focus-card audio-tracks-card">
      <div class="audio-card-head">
        <h3>Voice &amp; Music tracks</h3>
        <span class="audio-head-actions">
          <button class="btn small" type="button" data-action="add-music">${icon('volume', 12)} Add music</button>
          <button class="btn small" type="button" data-action="sfx-add" data-kind="sound">${icon('sparkle', 12)} Add sound</button>
          <button class="btn small primary" type="button" data-action="audio-mix-preview">${icon('play', 12)} ${mixing ? 'Stop' : 'Preview mix'}</button>
        </span>
      </div>
      <p class="small muted">Each row sets its own Start and Length; M mutes it, S solos it, and play auditions it alone.</p>
      ${rows.length ? `<div class="audio-placement" aria-label="Where each track sits in the project">
        ${rows.map((row) => `<div class="audio-placement-row">
          <span class="audio-placement-name" title="${esc(row.name || row.kind)}">${esc(row.name || row.kind)}</span>
          <span class="audio-placement-lane"><span class="audio-placement-bar" style="left:${pct(row.start)}%;width:${Math.max(1.5, pct(row.duration))}%;background:${row.color}"></span>${ticks.map((tick) => `<span class="audio-placement-tick" style="left:${pct(tick.at)}%" title="${esc(tick.label)}"></span>`).join('')}</span>
          <span class="audio-placement-time">${short(row.start)}–${short(Number(row.start || 0) + Number(row.duration || 0))}</span>
        </div>`).join('')}
        <div class="audio-placement-scale"><span>0:00</span><span>${short(span)}</span></div>
      </div>` : ''}
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
            <label>Volume <span class="audio-value">${level(row.volume, 0.25)}</span><input type="range" min="0" max="1.5" step="0.01" value="${Number(row.volume ?? 0.25)}" data-audio-field="volume" data-track="${esc(row.id)}"><span class="audio-value-scale"><span>0</span><span>100%</span><span>150%</span></span></label>
            <label>Fade in<input type="number" min="0" step="0.05" value="${Number(row.fade_in || 0).toFixed(2)}" data-audio-field="fade_in" data-track="${esc(row.id)}"></label>
            <label>Fade out<input type="number" min="0" step="0.05" value="${Number(row.fade_out || 0).toFixed(2)}" data-audio-field="fade_out" data-track="${esc(row.id)}"></label>
          </div>
        </details>`).join('') : `<div class="audio-empty">
          <p class="small muted">No voice, music or sound tracks yet. Start with Add music or Add sound above, or build a voice-over in the Voice &amp; dub card.</p>
        </div>`}
      </div>
    </div>
    <div class="focus-card audio-source-card">
      <h3>Original audio</h3>
      <div class="audio-status"><span class="chip ${bed.tone}">${bed.text}</span><span class="small muted">${bed.note}</span></div>
      <ul class="audio-mix-readout">
        <li><span>Source bed</span><strong>${bed.text}</strong></li>
        <li><span>Voice / dub</span><strong>${voices.length ? voices.map((row) => `${esc(row.name || row.kind)} ${level(row.volume, 1)}`).join(' · ') : 'none'}</strong></li>
        <li><span>Music</span><strong>${musicRow ? `${esc(musicRow.name || 'Music')} ${level(musicRow.volume, 0.25)}` : music ? `Music ${level(music.volume, 0.25)}` : 'none'}</strong></li>
      </ul>
      <button class="btn wide" type="button" data-action="audio-source-mute">${icon('volume', 13)} ${sourceMuted ? 'Unmute original audio' : 'Mute original audio'}</button>
    </div>
    <div class="focus-card">
      <h3>Voice & dub</h3>
      <div class="audio-status"><span class="chip ${voice || dub ? 'green' : ''}">${dub ? 'Dub built' : voice ? 'Voice-over' : 'None'}</span><span class="small muted">${voice ? esc(voice.voice || '') : ''}</span></div>
      ${voicePanel}
    </div>
    <div class="focus-card">
      <h3>Music & SFX</h3>
      ${musicRow ? `<div class="kv"><span>${esc(musicRow.name || 'Music')} · ${level(musicRow.volume, 0.25)}</span><button class="btn small" data-action="audio-remove" data-track="${esc(musicRow.id)}">Remove</button></div>` : music ? `<div class="kv"><span>${esc(music.name || 'Music')} · ${level(music.volume, 0.25)}</span><button class="btn small" data-action="remove-music">Remove</button></div>` : `<button class="btn wide" data-action="add-music">${icon('volume', 14)} Add music</button>`}
      <div class="sfx-list" style="margin-top:10px">
        ${sounds.map((fx) => `<div class="sfx-row"><span class="sfx-kind">sound</span><span class="sfx-name">${esc(fx.name || 'Sound')}</span><button class="icon-btn" data-action="sfx-remove" data-effect="${esc(fx.id)}">${icon('trash', 14)}</button></div>`).join('') || '<p class="small muted">No sound effects yet.</p>'}
      </div>
      <button class="btn wide" data-action="sfx-add" data-kind="sound">${icon('volume', 14)} Add sound effect</button>
    </div>
  </div>`;
}
