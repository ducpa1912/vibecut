"""Routes the Classic view adds from now on (lane: ``classic``).

New Classic endpoints go here, not into ``app.py``, so the lanes stop
editing the same file (see ``docs/branching.md``). Existing Classic routes
stay in ``app.py`` until someone has a reason to touch them. Use
``import app`` inside a handler when it needs app helpers; importing at
module level would be circular.
"""

from __future__ import annotations

import hashlib
import threading
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

router = APIRouter()

# Sound previews are short, cached and local. A provider call is made only
# when the generated-music cache has no file for this prompt, and the request
# is hard-bounded by both the preview length and the provider timeout.
PREVIEW_SECONDS = 12.0
PREVIEW_MAX_SECONDS = 20.0
PREVIEW_TIMEOUT = 90
PREVIEW_LOCK = threading.Lock()


@router.get("/classic")
def classic_page():
    """Serve Classic's own page; Studio-only builds answer 404."""
    import editions

    if "classic" not in editions.views():
        raise HTTPException(404, "Not found")
    import app

    return app.page_response(app.STATIC / "classic" / "index.html")


class ExportCutBody(BaseModel):
    """A Classic export that carries the cut on screen, not just a target."""

    target: int = 30
    order: str = "source"
    hook_scene: int | None = None
    clips: list[dict] | None = None
    caption_track_id: str | None = None


@router.get("/api/classic/packs")
def classic_packs() -> dict:
    """Optional pack status for Classic Setup: on disk or not, no install."""
    import packs

    return {"packs": [{**pack, **_pack_usable(pack.get("id"))} for pack in packs.list_packs()]}


def _pack_usable(pack_id: str | None) -> dict:
    """Whether the engines a pack would add already work without the pack.

    A Mac with Whisper or Demucs installed some other way (pip, Homebrew) can
    transcribe or separate today; Setup must not tell a tester otherwise.
    """
    import audio
    import pipeline

    try:
        if pack_id == "speech":
            ready = any(item.get("cached") for item in pipeline.whisper_models())
            detail = "Whisper is already on this Mac."
        elif pack_id == "voice":
            ready = bool(((audio.engine_status().get("voices") or {}).get("kokoro") or {}).get("available"))
            detail = "Kokoro voices are already on this Mac."
        elif pack_id == "separation":
            engines = (audio.engine_status().get("separation") or {}).values()
            ready = any(bool((item or {}).get("available")) for item in engines)
            detail = "Voice separation is already on this Mac."
        else:
            return {"usable": False}
    except Exception:  # noqa: BLE001 - status only; never fail Setup over it
        return {"usable": False}
    return {"usable": ready, "usable_detail": detail if ready else ""}


@router.post("/api/classic/jobs/{job_id}/export/{kind}")
def export_edited_cut(job_id: str, kind: str, body: ExportCutBody):
    """Export SRT, VTT, EDL or XML from the edited clips the browser sends.

    The legacy GET takes only target/order/hook, so an edited cut or a loaded
    variant exported the automatic plan. This route reuses the same export
    builder with ``_custom_plan``.
    """
    import app

    if kind not in {"srt", "vtt", "edl", "xml"}:
        raise HTTPException(404, "Unknown export format.")
    job = app.load_job(job_id)
    target = app._valid_target(int(body.target))
    plan_body = app.PlanBody(
        target=target,
        hook_scene=body.hook_scene,
        order=body.order,
        clips=body.clips,
    )
    plan = app._plan_for_body(job, target, plan_body)
    return app._export_plan_response(
        job_id, job, plan, kind, target, body.caption_track_id,
    )


# ---------------------------------------------------------------- translation warm-up

TRANSLATION_BATCH = 20
TRANSLATION_RUNS: dict[tuple[str, str], dict] = {}
TRANSLATION_LOCK = __import__("threading").Lock()


class TranslateBody(BaseModel):
    target: str
    provider: str = "auto"


def _translation_texts(job_id: str) -> list[str]:
    import pipeline

    segments = pipeline.read_transcript(_translation_job_dir(job_id)) or []
    return [
        str(segment.get("text") or "").strip()
        for segment in segments
        if str(segment.get("text") or "").strip()
    ]


def _translation_job_dir(job_id: str):
    import app

    return app._job_dir(job_id)


def _translation_source(job_id: str) -> str:
    import app

    job = app.load_job(job_id)
    return str(
        ((job.get("analysis") or {}).get("engine") or {}).get("transcript_language")
        or "en"
    ).split("-")[0]


def _translation_hash(texts: list[str]) -> str:
    import hashlib

    return hashlib.sha1("\n".join(texts).encode("utf-8")).hexdigest()[:20]


def _translation_flag(job_id: str, target: str):
    return _translation_job_dir(job_id) / "translations" / f"{target}.json"


def _translation_state(job_id: str, target: str) -> dict:
    import json

    target = str(target or "").split("-")[0]
    source = _translation_source(job_id)
    texts = _translation_texts(job_id)
    total = len(texts)
    batches = (total + TRANSLATION_BATCH - 1) // TRANSLATION_BATCH
    key = (job_id, target)
    with TRANSLATION_LOCK:
        running = dict(TRANSLATION_RUNS.get(key) or {})
    # A finished run is not proof by itself: the transcript can change under
    # it. Only live or failed work wins over the flag check below.
    if running and running.get("status") in {"running", "failed"}:
        return running
    if not target or target == source:
        return {
            "job_id": job_id, "target": target, "status": "ready",
            "done": 0, "total": 0, "batch": 0, "batches": 0,
            "provider": "none", "error": None,
        }
    path = _translation_flag(job_id, target)
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        saved = None
    if saved and saved.get("source_hash") == _translation_hash(texts):
        return {**saved, "status": "ready", "done": total, "total": total,
                "batch": batches, "batches": batches}
    return {
        "job_id": job_id, "target": target, "status": "idle",
        "done": 0, "total": total, "batch": 0, "batches": batches,
        "provider": "auto", "error": None,
    }


def _set_run(job_id: str, target: str, **values) -> dict:
    key = (job_id, target)
    with TRANSLATION_LOCK:
        current = dict(TRANSLATION_RUNS.get(key) or {})
        current.update(values)
        TRANSLATION_RUNS[key] = current
        return dict(current)


def _translation_worker(
    job_id: str, target: str, provider: str, source: str, texts: list[str],
) -> None:
    import json
    import time
    import uuid

    started = time.time()
    total = len(texts)
    batches = (total + TRANSLATION_BATCH - 1) // TRANSLATION_BATCH
    for index in range(batches):
        chunk = texts[index * TRANSLATION_BATCH:(index + 1) * TRANSLATION_BATCH]
        try:
            import audio

            audio.translate_lines(chunk, source, target, provider or "auto")
        except Exception as exc:  # noqa: BLE001 - status carries the reason
            _set_run(
                job_id, target, status="failed", done=index * TRANSLATION_BATCH,
                batch=index, batches=batches, error=str(exc)[:400],
                latency_ms=round((time.time() - started) * 1000),
            )
            return
        _set_run(
            job_id, target, status="running",
            done=min((index + 1) * TRANSLATION_BATCH, total),
            batch=index + 1, batches=batches, error=None,
        )
    finished = {
        "job_id": job_id, "target": target, "status": "ready",
        "done": total, "total": total, "batch": batches, "batches": batches,
        "provider": provider or "auto", "error": None,
        "source": source, "source_hash": _translation_hash(texts),
        "lines": total, "completed_at": round(time.time(), 3),
        "latency_ms": round((time.time() - started) * 1000),
    }
    try:
        path = _translation_flag(job_id, target)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(finished, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass
    _set_run(
        job_id, target,
        **{key: value for key, value in finished.items() if key not in ("job_id", "target")},
    )
    try:
        import app

        app._history_append(job_id, {
            "id": uuid.uuid4().hex[:12],
            "type": "translation",
            "created": round(time.time(), 3),
            "status": "ok",
            "target": 0,
            "style": None,
            "source_lang": source,
            "target_lang": target,
            "provider": provider or "auto",
            "fallback": False,
            "tried": [],
            "model": None,
            "latency_ms": finished["latency_ms"],
            "usage": {},
            "warning": None,
            "error": None,
            "path": None,
            "script_id": None,
            "clip_hash": None,
        })
    except Exception:  # noqa: BLE001 - history is best effort
        pass


@router.post("/api/classic/jobs/{job_id}/translate")
def classic_translate(job_id: str, body: TranslateBody) -> dict:
    """Translate the full transcript once, in 20-line batches, in the background."""
    import threading

    target = str(body.target or "").split("-")[0]
    if not target:
        raise HTTPException(400, "Choose a language first.")
    source = _translation_source(job_id)
    if target == source:
        return _translation_state(job_id, target)
    existing = _translation_state(job_id, target)
    if existing.get("status") == "ready":
        return existing
    texts = _translation_texts(job_id)
    if not texts:
        raise HTTPException(409, "This video has no transcript to translate.")
    key = (job_id, target)
    with TRANSLATION_LOCK:
        if key in TRANSLATION_RUNS and TRANSLATION_RUNS[key].get("status") == "running":
            return dict(TRANSLATION_RUNS[key])
        TRANSLATION_RUNS[key] = {
            "job_id": job_id, "target": target, "status": "running",
            "done": 0, "total": len(texts), "batch": 0,
            "batches": (len(texts) + TRANSLATION_BATCH - 1) // TRANSLATION_BATCH,
            "provider": body.provider or "auto", "error": None,
        }
    threading.Thread(
        target=_translation_worker,
        args=(job_id, target, body.provider or "auto", source, texts),
        name=f"translate-{job_id}-{target}",
        daemon=True,
    ).start()
    return _translation_state(job_id, target)


@router.get("/api/classic/jobs/{job_id}/translate/status")
def classic_translate_status(job_id: str, target: str = "") -> dict:
    return _translation_state(job_id, target)


# ---------------------------------------------------------------- sound previews


class MusicPreviewBody(BaseModel):
    """One bounded AI music preview for the Classic Sound card."""

    engine: str = "minimax-music"
    prompt: str = ""
    moods: list[str] = []
    seconds: float | None = None


def _preview_seconds(value: float | None, default: float = PREVIEW_SECONDS) -> float:
    try:
        seconds = float(value if value is not None else default)
    except (TypeError, ValueError):
        seconds = default
    return round(max(3.0, min(PREVIEW_MAX_SECONDS, seconds)), 2)


def _preview_cache_dir() -> Path:
    import audio

    directory = audio.CACHE / "classic-preview"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _preview_key(label: str, source: Path, seconds: float) -> str:
    try:
        stat = source.stat()
        stamp = f"{source.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
    except OSError:
        stamp = str(source)
    return hashlib.sha1(f"{label}|{stamp}|{seconds:.2f}".encode()).hexdigest()[:24]


def _write_preview(source: Path, target: Path, seconds: float) -> Path:
    """Trim and fade a local file into a small WAV preview."""
    import audio

    duration = audio.media_duration(source)
    clip = seconds if duration <= 0.05 else min(seconds, duration)
    clip = max(0.25, clip)
    filters = ["aresample=48000"]
    if clip > 0.8:
        filters.insert(0, f"afade=t=out:st={clip - 0.35:.3f}:d=0.35")
    tmp = target.with_name(f".{target.stem}.{uuid.uuid4().hex}.part.wav")
    try:
        audio._run([
            audio._ffmpeg(), "-y", "-v", "error", "-i", str(source),
            "-t", f"{clip:.3f}", "-ac", "2", "-af", ",".join(filters),
            "-c:a", "pcm_s16le", str(tmp),
        ], timeout=PREVIEW_TIMEOUT)
        tmp.replace(target)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    return target


def _cached_preview(
    label: str, source: Path, seconds: float,
) -> tuple[Path, str]:
    """Return a cached preview or make one. Returns (path, cache state)."""
    cache = _preview_cache_dir()
    target = cache / f"{_preview_key(label, source, seconds)}.wav"
    if target.is_file() and target.stat().st_size > 512:
        return target, "hit"
    with PREVIEW_LOCK:
        if target.is_file() and target.stat().st_size > 512:
            return target, "hit"
        try:
            _write_preview(source, target, seconds)
        except Exception as exc:  # noqa: BLE001 - route reports the reason
            raise HTTPException(400, f"Could not build the audio preview: {str(exc)[:240]}") from exc
    return target, "miss"


def _job_file(job_id: str, value: str) -> Path:
    import app

    root = app._job_dir(job_id).resolve()
    candidate = Path(str(value or ""))
    if not candidate.is_absolute():
        candidate = root / candidate
    resolved = candidate.resolve()
    if resolved != root and root not in resolved.parents:
        raise HTTPException(400, "Music path must be inside this job.")
    if not resolved.is_file():
        raise HTTPException(404, "That BGM file is missing. Choose it again.")
    return resolved


def _library_track(source: str, track: str, moods: list[str]) -> Path:
    import audio

    if source not in audio.MUSIC_DIRS:
        raise HTTPException(400, "Choose the library or upload your own BGM.")
    directory = audio.MUSIC_DIRS[source].resolve()
    if track:
        candidate = Path(track)
        if not candidate.is_absolute():
            candidate = directory / candidate
        resolved = candidate.resolve()
        if resolved != directory and directory not in resolved.parents:
            raise HTTPException(400, "That track is outside the music library.")
        if not resolved.is_file():
            raise HTTPException(404, "That track is missing from the music library.")
        return resolved
    picked = audio.pick_music(audio.list_music(source), moods)
    if not picked:
        raise HTTPException(
            404,
            f"No tracks in {directory}. Drop an audio file there or upload your BGM.",
        )
    return Path(picked["id"])


def _bgm_preview_source(
    job_id: str, source: str, track: str, upload: str, moods: list[str],
) -> Path:
    source = str(source or "library").strip().lower()
    if source == "upload":
        if not upload:
            raise HTTPException(400, "Choose your BGM file first.")
        return _job_file(job_id, upload)
    return _library_track(source, track, moods)


def _generated_music_preview(body: MusicPreviewBody) -> tuple[Path, str]:
    """Generate one short preview, cached by engine and prompt.

    The file is cached before the provider is called again. The provider is
    reached only on a cache miss, with a 90 s timeout and a bounded length.
    """
    import audio
    import music

    engine = str(body.engine or "").strip().lower()
    allowed = {"minimax-music", "lyria-clip"}
    if engine not in allowed:
        raise HTTPException(400, "Choose MiniMax Music or OpenRouter Lyria.")
    info = (audio.engine_status().get("music") or {}).get(engine) or {}
    if not info.get("available"):
        raise HTTPException(
            409,
            "AI music needs a MiniMax or OpenRouter key. Add one in Setup or use my BGM.",
        )
    seconds = _preview_seconds(body.seconds)
    moods = [str(mood).strip()[:40] for mood in (body.moods or []) if str(mood).strip()][:6]
    prompt = " ".join(str(body.prompt or "").split())[:300]
    if not prompt:
        prompt = audio.music_prompt(moods, seconds)
    if f"{seconds:.0f}" not in prompt:
        prompt = f"{prompt}, {seconds:.0f}-second instrumental preview"
    cache = _preview_cache_dir()
    key = hashlib.sha1(
        f"music|{engine}|{prompt}|{seconds:.2f}".encode(),
    ).hexdigest()[:24]
    target = cache / f"music-{key}.wav"
    if target.is_file() and target.stat().st_size > 1024:
        return target, "hit"
    with PREVIEW_LOCK:
        if target.is_file() and target.stat().st_size > 1024:
            return target, "hit"
        try:
            raw = music.generate_music(
                engine, prompt, seconds, timeout=PREVIEW_TIMEOUT,
            )
        except audio.AudioError as exc:
            raise HTTPException(409, str(exc)[:400]) from exc
        if not raw or not Path(raw).is_file():
            raise HTTPException(502, "Music generation returned no file.")
        try:
            _write_preview(Path(raw), target, seconds)
        except Exception as exc:  # noqa: BLE001 - route reports the reason
            raise HTTPException(400, f"Could not build the music preview: {str(exc)[:240]}") from exc
    return target, "miss"


@router.get("/api/classic/jobs/{job_id}/sound/bgm-preview")
def classic_bgm_preview(
    job_id: str,
    source: str = "library",
    track: str = "",
    upload: str = "",
    moods: str = "",
    seconds: float = PREVIEW_SECONDS,
) -> FileResponse:
    """Play the chosen BGM as a bounded local preview, never a provider call."""
    import app

    app.load_job(job_id)
    mood_list = [item.strip()[:40] for item in str(moods or "").split(",") if item.strip()][:6]
    path = _bgm_preview_source(job_id, source, track, upload, mood_list)
    preview, cache_state = _cached_preview("bgm", path, _preview_seconds(seconds))
    return FileResponse(
        preview,
        media_type="audio/wav",
        filename="bgm-preview.wav",
        headers={
            "Cache-Control": "private, max-age=3600",
            "X-VibeCut-Preview": cache_state,
        },
    )


@router.post("/api/classic/jobs/{job_id}/sound/music-preview")
def classic_music_preview(job_id: str, body: MusicPreviewBody) -> FileResponse:
    """Generate or replay one short AI music preview, cached by prompt."""
    import app

    app.load_job(job_id)
    path, cache_state = _generated_music_preview(body)
    return FileResponse(
        path,
        media_type="audio/wav",
        filename="music-preview.wav",
        headers={
            "Cache-Control": "private, max-age=3600",
            "X-VibeCut-Preview": cache_state,
        },
    )
