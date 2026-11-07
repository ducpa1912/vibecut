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
    items: unknown[];
  };
  detection: null;
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
