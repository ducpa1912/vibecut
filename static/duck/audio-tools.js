export function waveformPeaks(channel, bufferDuration, offset, duration, count) {
  const total = Math.max(0.01, Number(bufferDuration) || 0.01);
  const startAt = Math.min(
    channel.length - 1,
    Math.floor((Math.max(0, offset) / total) * channel.length),
  );
  const endAt = Math.min(
    channel.length,
    startAt + Math.floor((Math.max(0.05, duration) / total) * channel.length),
  );
  const block = Math.max(1, Math.floor((endAt - startAt) / count));
  return Array.from({ length: count }, (_unused, index) => {
    const from = startAt + index * block;
    const to = Math.min(endAt, from + block);
    let peak = 0;
    for (let at = from; at < to; at += Math.max(1, Math.floor(block / 24))) {
      peak = Math.max(peak, Math.abs(channel[at] || 0));
    }
    return Math.min(1, peak * 3.2);
  });
}

export function audibleRows(rows = []) {
  const solo = rows.filter((row) => row.solo);
  return solo.length ? solo : rows;
}

export function mixEntry(row, playhead, bufferDuration) {
  const rowStart = Number(row.start || 0);
  const rowEnd = rowStart + Number(row.duration ?? 0.2);
  if (rowEnd <= playhead) return null;
  const inside = rowStart <= playhead;
  const delay = inside ? 0 : rowStart - playhead;
  const offset = Math.max(0, Number(row.offset || 0) + (inside ? playhead - rowStart : 0));
  if (offset >= bufferDuration) return null;
  const wanted = rowEnd - Math.max(rowStart, playhead);
  const duration = Math.min(wanted, bufferDuration - offset);
  const level = Math.max(
    0,
    Math.min(1.5, Number(row.volume ?? (row.kind === 'music' ? 0.25 : 1))),
  );
  const total = Number(row.fade_duration ?? row.duration);
  const phase = Number(row.fade_offset || 0) + Math.max(0, playhead - rowStart);
  const attack = Math.min(total / 2, Number(row.fade_in || 0));
  const release = Math.min(total / 2, Number(row.fade_out || 0));
  const points = [phase, ...[attack, total - release].filter(t => t > phase && t < phase + duration), phase + duration];
  const envelope = points.map(t => [t - phase, level * Math.max(0, Math.min(
    1, attack ? t / attack : 1, release ? (total - t) / release : 1))]);
  return { delay, offset, duration, level, envelope };
}

// Draw from the source envelope. Average five 10 ms samples at each plotted point.
export function drawLevels(canvas, values, offset, duration, gain, highlights = []) {
  const width = Math.max(1, Math.round(canvas.clientWidth * devicePixelRatio));
  const height = Math.max(2, Math.round(canvas.clientHeight * devicePixelRatio));
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');
  const mid = height / 2;
  ctx.fillStyle = '#d58a32';
  for (const [a, b] of highlights) {
    ctx.fillRect(a / duration * width, 0, (b - a) / duration * width, height);
  }
  ctx.fillStyle = getComputedStyle(canvas).color;
  const amplitudes = new Float32Array(width);
  for (let x = 0; x < width; x++) {
    const index = Math.floor((offset + x / width * duration) * 100);
    let sum = 0;
    let count = 0;
    for (let i = Math.max(0, index - 2); i <= Math.min(values.length - 1, index + 2); i++) {
      sum += values[i];
      count++;
    }
    amplitudes[x] = Math.max(0.5, Math.min(1, 2 * gain * sum / (count || 1)) * mid * .92);
  }
  ctx.beginPath();
  ctx.moveTo(0, mid);
  for (let x = 0; x < width; x++) ctx.lineTo(x, mid - amplitudes[x]);
  for (let x = width - 1; x >= 0; x--) ctx.lineTo(x, mid + amplitudes[x]);
  ctx.closePath();
  ctx.fill();
}
