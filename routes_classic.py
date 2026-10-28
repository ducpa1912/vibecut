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


class ExportCutBody(BaseModel):
    """A Classic export that carries the cut on screen, not just a target."""

    target: int = 30
    order: str = "source"
    hook_scene: int | None = None
    clips: list[dict] | None = None
    caption_track_id: str | None = None


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
