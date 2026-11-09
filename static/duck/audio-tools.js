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
  const rowEnd = rowStart + Math.max(0.2, Number(row.duration || 0.2));
  if (rowEnd <= playhead) return null;
  const inside = rowStart <= playhead;
  const delay = inside ? 0 : rowStart - playhead;
  const offset = Math.max(0, Number(row.offset || 0) + (inside ? playhead - rowStart : 0));
  if (offset >= bufferDuration - 0.01) return null;
  const wanted = Math.max(0.05, rowEnd - Math.max(rowStart, playhead));
  const duration = Math.min(wanted, bufferDuration - offset);
  const level = Math.max(
    0,
    Math.min(1.5, Number(row.volume ?? (row.kind === 'music' ? 0.25 : 1))),
  );
  const fadeIn = Math.max(0, Math.min(duration / 2, Number(row.fade_in || 0)));
  const fadeOut = Math.max(0, Math.min(duration / 2, Number(row.fade_out || 0)));
  return { delay, offset, duration, level, fadeIn, fadeOut };
}
