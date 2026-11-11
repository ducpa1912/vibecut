export type LibraryStatus =
  | 'uploading'
  | 'uploaded'
  | 'probing'
  | 'dissecting'
  | 'ready'
  | 'upload_incomplete'
  | 'failed'
  | 'deleting';

export type ErrorAction =
  | 'none'
  | 'sign_in'
  | 'retry'
  | 'reload_detection'
  | 'upgrade_plan'
  | 'choose_engine'
  | 'reselect_range'
  | 'reupload'
  | 'contact_support';

export interface ApiErrorBody {
  code: string;
  message: string;
  detail: Record<string, unknown>;
  retryable: boolean;
  action: ErrorAction;
}

export interface ApiErrorEnvelope {
  error: ApiErrorBody;
}

export interface UploadTicket {
  upload_id: string;
  library_item_id: string;
  source_asset_id: string;
  method: 'PUT';
  url: string;
  headers: Record<string, string>;
  expires_at: string;
  max_bytes: number;
}

export interface LibraryItem {
  id: string;
  title: string;
  status: LibraryStatus;
  error: ApiErrorBody | null;
  created_at: string;
  updated_at: string;
  duration_ms: number | null;
  width: number | null;
  height: number | null;
  fps: number | null;
  has_audio: boolean | null;
  bytes: number | null;
  poster_url: string | null;
  poster_expires_at: string | null;
  detection_revision: string | null;
  render_job_id: string | null;
  render_status: string | null;
}

export interface LibraryPage {
  items: LibraryItem[];
  next_cursor: string | null;
}

export interface ProbeInfo {
  duration_ms: number;
  display_width: number;
  display_height: number;
  rotation: number;
  fps: number;
  fps_num: number;
  fps_den: number;
  frame_count: number;
  video_codec: string;
  pixel_format: string;
  audio_codec: string | null;
  has_audio: boolean;
}

export interface ProxyInfo {
  id: string;
  width: number;
  height: number;
  duration_ms: number;
  fps: number;
  bytes: number;
}

export interface DetectionRange {
  beat_id: string;
  beat_index: number;
  start_frame: number;
  end_frame: number;
}

export interface DetectionMaskRef {
  id: string;
  kind: 'glyph' | 'region' | 'feather';
  format: 'png' | 'webp';
  url: string | null;
  expires_at: string | null;
  provenance: 'ocr' | 'logo' | 'user_box' | 'manual';
  model_version: string;
}

export interface DetectionMember {
  id: string;
  text: string | null;
  range_mode: 'ranges' | 'whole_source';
  ranges: DetectionRange[];
  box: { x: number; y: number; w: number; h: number };
  confidence: number;
  provenance: 'ocr' | 'logo' | 'user_box' | 'manual';
  mask: DetectionMaskRef | null;
  included_default: boolean;
  low_confidence: boolean;
  fill_keys: number[];
}

export interface DetectionGroup {
  id: string;
  kind: 'text' | 'logo' | 'watermark' | 'image' | 'user_box';
  lane: number;
  order_index: number;
  sample_text: string | null;
  box: { x: number; y: number; w: number; h: number };
  confidence: number;
  member_count: number;
  included_default: boolean;
  low_confidence: boolean;
  members: DetectionMember[];
}

export interface DetectionRunInfo {
  id: string;
  revision: string;
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';
  progress: number;
  engine: 'auto' | 'paddleocr' | 'rapidocr';
  model_versions: Record<string, string>;
  frames_read: number;
  frames_skipped: number;
  frames_total: number;
  effective_fps: number | null;
  coverage: number | null;
  truncated: boolean;
  ocr_available: boolean;
  logo_model_available: boolean;
  warnings: string[];
  compute_seconds: number;
  device_class: 'cpu' | 'gpu_standard' | 'gpu_premium' | null;
  error: { code: string; message: string } | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface DetectionBeat {
  beat_id: string;
  index: number;
  start_ms: number;
  end_ms: number;
  status: 'pending' | 'ready' | 'empty' | 'failed';
  has_target: boolean;
}

export interface DetectionView {
  run: DetectionRunInfo | null;
  groups: DetectionGroup[];
  beats: DetectionBeat[];
  selection_counts: { groups: number; members: number; beats_with_target: number };
}

export interface LibraryDetail extends LibraryItem {
  source: {
    id: string;
    filename: string;
    content_type: string;
    bytes: number;
    etag: string | null;
    sha256: string | null;
    upload_status: 'pending' | 'completed' | 'abandoned';
    probe_status: 'pending' | 'running' | 'succeeded' | 'failed';
    dissect_status: 'pending' | 'running' | 'succeeded' | 'failed';
    beat_manifest_hash: string | null;
  };
  proxy: ProxyInfo | null;
  probe: ProbeInfo | null;
  beats: {
    total: number;
    with_target: number;
    manifest_hash: string | null;
    items: DetectionBeat[];
  };
  detection: DetectionView | null;
  render: null;
}

export interface PlayTicket {
  url: string;
  expires_at: string;
  duration_ms: number;
  width: number;
  height: number;
}

export interface Me {
  id: string;
  email: string | null;
  display_name: string | null;
  avatar_url: string | null;
  plan: 'free' | 'pro' | 'studio';
  render_seconds_balance: number;
  storage_bytes_used: number;
  storage_bytes_limit: number;
  monthly_render_hours: number;
}

export type UploadPhase =
  'signing' | 'uploading' | 'verifying' | 'done' | 'failed' | 'cancelled';

export interface UploadState {
  file: File;
  phase: UploadPhase;
  ticket: UploadTicket | null;
  loaded: number;
  total: number;
  started_at: number;
  error: string | null;
}
