"""Routes the Classic view adds from now on (lane: ``classic``).

New Classic endpoints go here, not into ``app.py``, so the lanes stop
editing the same file (see ``docs/branching.md``). Existing Classic routes
stay in ``app.py`` until someone has a reason to touch them. Use
``import app`` inside a handler when it needs app helpers; importing at
module level would be circular.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


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
