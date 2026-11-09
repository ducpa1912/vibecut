export function clipDuration(clip) {
  return Math.max(0, Number(clip?.end || 0) - Number(clip?.start || 0));
}

export function storyDuration(clips = []) {
  return clips.reduce((sum, clip) => sum + clipDuration(clip), 0);
}

export function storyClipAt(clips = [], time = 0) {
  let cursor = 0;
  for (let index = 0; index < clips.length; index += 1) {
    const clip = clips[index];
    const duration = clipDuration(clip);
    if (Number(time) < cursor + duration || index === clips.length - 1) {
      return { clip, index, start: cursor, offset: Math.max(0, Number(time) - cursor) };
    }
    cursor += duration;
  }
  return null;
}

export function timelineToSource(clips = [], time = 0) {
  let cursor = 0;
  for (const clip of clips) {
    const duration = clipDuration(clip);
    if (Number(time) < cursor + duration) {
      return Number(clip.start || 0) + (Number(time) - cursor);
    }
    cursor += duration;
  }
  const last = clips.slice(-1)[0];
  return Number(last?.end || 0);
}

export function sourceToTimeline(clips = [], time = 0) {
  let cursor = 0;
  for (const clip of clips) {
    const start = Number(clip.start || 0);
    const end = Number(clip.end || 0);
    if (Number(time) >= start && Number(time) < end) {
      return cursor + (Number(time) - start);
    }
    cursor += Math.max(0, end - start);
  }
  return cursor;
}

export function storyRanges(clips = [], byId = new Map()) {
  let cursor = 0;
  return clips.map((clip, index) => {
    const start = cursor;
    cursor += clipDuration(clip);
    return { scene: byId.get(clip.scene), clip, index, start, end: cursor };
  });
}
