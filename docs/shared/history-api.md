# Job history API

Per-job history is stored outside `job.json`:

```
data/jobs/<job_id>/history/index.json        # newest-first summaries (capped)
data/jobs/<job_id>/history/<entry_id>.json   # full snapshot for one entry
```

`job.json`, `GET /api/jobs/{id}` and `GET /api/jobs/{id}/status` do **not**
include history or snapshots. Old jobs without a `history/` directory return an
empty list. The default cap is 50 entries per job; set `VIBECUT_HISTORY_MAX` to
change it (hard maximum 200). Pruning removes the oldest summary and its
snapshot file.

Every write is atomic (temp file + `os.replace`), and index updates are
serialised with a process-wide lock. Secret-shaped keys and values are removed
before anything is written.

## Summary fields

`GET /api/jobs/{job_id}/history` returns summaries newest first:

```json
{
  "entries": [
    {
      "id": "a1b2c3d4e5f6",
      "type": "script",
      "created": 1760000000.123,
      "status": "ok",
      "target": 30,
      "style": "smooth",
      "source_lang": "en",
      "target_lang": "vi",
      "provider": "opencode",
      "fallback": false,
      "tried": ["openrouter"],
      "model": "deepseek-v4.1-flash",
      "latency_ms": 812,
      "usage": {
        "calls": 2,
        "input_tokens": 900,
        "output_tokens": 220,
        "chars": 0,
        "audio_seconds": 0.0,
        "cost_usd": 0.000267
      },
      "warning": null,
      "error": null,
      "path": null,
      "script_id": "a1b2c3d4e5f6",
      "clip_hash": "7f3c0f1d2e4a5b6c"
    }
  ],
  "count": 1
}
```

Optional query: `?limit=10` (1..200).

Entry types: `script`, `translation`, `rewrite`, `render`, `upload`. `test` is reserved for provider checks.

Common statuses: `ok`, `fallback`, `failed`, `queued`, `ready`, `cancelled`.

Render summaries additionally carry `quality`, `aspect`, `audio_sig` and
`record_key`. Upload summaries carry `kind` (`voice` or `music`), `name` and
`duration`.

## Get one entry

`GET /api/jobs/{job_id}/history/{entry_id}`:

```json
{
  "entry": { "...": "same summary shape as above" },
  "snapshot": { "...": "type-specific payload" }
}
```

404 when the entry or its snapshot does not exist.

## Restore

`POST /api/jobs/{job_id}/history/{entry_id}/restore` returns the same payload
plus `restored: true`:

```json
{
  "restored": true,
  "entry": { "...": "summary" },
  "snapshot": { "...": "type-specific payload" }
}
```

Restore **does not mutate** `job.json` or any live job field. The frontend
applies the snapshot (for example, restore script overrides/lines) through the
normal editing endpoints.

## Delete

`DELETE /api/jobs/{job_id}/history/{entry_id}`:

```json
{ "deleted": "a1b2c3d4e5f6" }
```

404 when the entry does not exist.

## Script snapshot

`POST /api/jobs/{job_id}/audio/script` now returns `script_id`. Its history
entry uses `id == script_id` and stores:

```json
{
  "script_id": "a1b2c3d4e5f6",
  "target": 30,
  "style": "smooth",
  "source_lang": "en",
  "target_lang": "vi",
  "overrides": { "12": "edited line" },
  "clip_hash": "7f3c0f1d2e4a5b6c",
  "original_lines": ["source line"],
  "literal_lines": ["translated line"],
  "final_lines": [
    {
      "scene": 12,
      "clip": 0,
      "text": "final line",
      "original": "source line",
      "literal": "translated line",
      "rewrite": "rules",
      "overridden": true
    }
  ],
  "translation": { "provider": "opencode", "tried": ["openrouter"] },
  "rewrite": {
    "provider": "rules",
    "used": "rules",
    "fallback": false,
    "attempts": [{ "provider": "opencode", "error": "" }]
  },
  "translated": true,
  "warning": null,
  "error": null,
  "provider": "opencode",
  "model": "deepseek-v4.1-flash",
  "tried": ["openrouter", "opencode"],
  "fallback": false,
  "total": 30.0,
  "moods": ["warm"],
  "usage": { "...": "usage delta for this request" },
  "latency_ms": 812
}
```

A failed request still appends a `status: "failed"` entry with `error` and the
same target/style/language fields. It never replaces an older successful
snapshot. A request that succeeds with a warning (for example translation
failed and literal text was kept) uses `status: "fallback"` and sets
`warning`.

## Render snapshot

Queued, ready, failed and cancelled renders each append a separate entry.
`script_id` comes from `PlanBody.script_id` or `audio.script_id`.

```json
{
  "render": {
    "status": "ready",
    "target": 30,
    "quality": "final",
    "aspect": "9:16",
    "audio_sig": "1a2b3c4d",
    "script_id": "a1b2c3d4e5f6",
    "path": "reel_30.mp4",
    "poster": "reel_30.jpg",
    "error": null
  },
  "plan": {
    "target": 30,
    "hook_scene": 4,
    "total": 30.0,
    "clip_count": 6,
    "order": "source",
    "clips": []
  },
  "script_id": "a1b2c3d4e5f6",
  "status": "ready",
  "error": null,
  "warning": null
}
```

## Upload snapshot

`POST /api/jobs/{job_id}/audio/voice-upload` and
`POST /api/jobs/{job_id}/audio/music-upload` append `type: "upload"` entries on
success and failure.

```json
{
  "kind": "voice",
  "name": "take.wav",
  "path": "audio/uploaded_voice_ab12cd34ef56.wav",
  "duration": 12.4,
  "size": 1187840,
  "status": "ok",
  "error": null
}
```
