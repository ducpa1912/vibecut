import type { LibraryDetail, LibraryItem, LibraryStatus } from './types';
import { formatBytes, formatDuration, formatFps } from './format';

/** Status presentation shared by the library row, the item header and polling. */

export function isPending(status: LibraryStatus): boolean {
  return status !== 'ready' && status !== 'failed' && status !== 'upload_incomplete';
}

export function statusLabel(status: LibraryStatus): string {
  switch (status) {
    case 'uploading':
      return 'Uploading';
    case 'uploaded':
      return 'Uploaded';
    case 'probing':
      return 'Reading';
    case 'dissecting':
      return 'Splitting beats';
    case 'ready':
      return 'Ready';
    case 'upload_incomplete':
      return 'Upload incomplete';
    case 'failed':
      return 'Failed';
    case 'deleting':
      return 'Deleting';
  }
}

export function tone(status: LibraryStatus): string {
  if (status === 'ready') return 'ready';
  if (status === 'failed' || status === 'upload_incomplete') return 'failed';
  if (
    status === 'uploading' ||
    status === 'uploaded' ||
    status === 'probing' ||
    status === 'dissecting'
  ) {
    return 'busy';
  }
  return 'muted';
}

/** The one-line measured summary under a library row. */
export function asRun(item: LibraryItem): string {
  const parts: string[] = [];
  if (item.duration_ms !== null) parts.push(`PROBE ${formatDuration(item.duration_ms)}`);
  if (item.width !== null && item.height !== null) {
    parts.push(`${item.width}×${item.height}`);
  }
  if (item.fps !== null) parts.push(formatFps(item.fps));
  if (item.bytes !== null) parts.push(formatBytes(item.bytes));
  return parts.join(' · ');
}

/** The same facts from the probe payload, for the item view. */
export function asRunDetail(item: LibraryDetail): string {
  const parts: string[] = [];
  const probe = item.probe;
  if (probe) {
    parts.push(`PROBE ${formatDuration(probe.duration_ms)}`);
    parts.push(`${probe.display_width}×${probe.display_height}`);
    parts.push(formatFps(probe.fps));
    parts.push(
      `${probe.video_codec.toUpperCase()}/${
        probe.has_audio ? (probe.audio_codec ?? 'audio').toUpperCase() : 'silent'
      }`,
    );
  }
  if (item.bytes !== null) parts.push(formatBytes(item.bytes));
  return parts.length > 0 ? parts.join(' · ') : 'Measured facts appear after the probe.';
}
