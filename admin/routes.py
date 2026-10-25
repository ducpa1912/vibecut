"""Password-only admin console routes under ``/_ductator``."""

from __future__ import annotations

import json
import threading
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import settings_store
import workflow_config
from admin import catalog, store

router = APIRouter(prefix="/_ductator/api", tags=["admin"])
COOKIE_NAME = "vibecut_admin"
COOKIE_PATH = "/_ductator"
CSRF_HEADER = "X-VibeCut-Admin-CSRF"

_LOCK = threading.Lock()
_ATTEMPTS: dict[str, list[float]] = {}
MAX_ATTEMPTS = 8
ATTEMPT_WINDOW = 15 * 60


class BootstrapBody(BaseModel):
    email: str
    password: str


class LoginBody(BaseModel):
    email: str
    password: str


class AccountBody(BaseModel):
    email: str
    current_password: str
    new_password: str = ""


class KeyBody(BaseModel):
    value: str = ""


class WorkflowBody(BaseModel):
    routes: list[dict] = []
    reasoning: str = ""
    max_output_tokens: int = 3200
    timeout_s: int = 300


def _client_ip(request: Request) -> str:
    return str(getattr(request.client, "host", "") or "")


def _local_bootstrap_allowed() -> bool:
    try:
        import app  # noqa: PLC0415
        return str(app.HOST) in {"127.0.0.1", "localhost", "::1"}
    except Exception:  # noqa: BLE001
        return False


def _audit(request: Request, actor: str, action: str, **kwargs: Any) -> None:
    store.record_audit(
        actor,
        action,
        ip=_client_ip(request),
        user_agent=str(request.headers.get("user-agent") or ""),
        **kwargs,
    )


def _session(request: Request) -> dict:
    token = str(request.cookies.get(COOKIE_NAME) or "")
    session = store.get_session(token)
    if not session:
        raise HTTPException(401, "Admin login required.")
    return session


def _csrf(request: Request, session: dict) -> None:
    supplied = str(request.headers.get(CSRF_HEADER) or "")
    if not supplied or supplied != str(session.get("csrf") or ""):
        raise HTTPException(403, "Invalid admin CSRF token.")


def _rate_key(request: Request, email: str) -> str:
    return f"{_client_ip(request)}|{str(email).strip().lower()}"


def _check_rate(request: Request, email: str) -> None:
    key = _rate_key(request, email)
    now = time.time()
    with _LOCK:
        attempts = [item for item in _ATTEMPTS.get(key, []) if now - item < ATTEMPT_WINDOW]
        _ATTEMPTS[key] = attempts
        if len(attempts) >= MAX_ATTEMPTS:
            raise HTTPException(429, "Too many login attempts. Try again later.")


def _record_failure(request: Request, email: str) -> None:
    key = _rate_key(request, email)
    with _LOCK:
        _ATTEMPTS.setdefault(key, []).append(time.time())


def _set_cookie(response: Response, token: str, request: Request) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=store.SESSION_HOURS * 3600,
        path=COOKIE_PATH,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
    )


def _clear_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path=COOKIE_PATH)


def _secret_info(name: str) -> dict[str, Any]:
    raw = settings_store.get_secret(name)
    source = settings_store.secret_source(name)
    meta = catalog.AI_SECRETS.get(name, {})
    return {
        "name": name,
        "label": meta.get("label") or name,
        "configured": bool(raw),
        "source": source,
        "masked": store.mask_secret(raw) if raw else "",
        "env": meta.get("env") or "",
    }


def _mirror_legacy_workflow(name: str, normalized: dict[str, Any]) -> None:
    route = (normalized.get("routes") or [{}])[0]
    provider = str(route.get("provider") or "")
    model = str(route.get("model") or "")
    if name == "tts":
        tts_provider = provider
        if provider == "openrouter":
            tts_provider = "fish" if "fish" in model.lower() else "gemini"
        elif provider == "local":
            tts_provider = model if model in {"kokoro", "piper", "say"} else "local"
        settings_store.save_settings({
            "tts": {"provider": tts_provider if tts_provider in {
                "minimax", "fish", "gemini", "kokoro", "piper", "say", "local", "auto",
            } else "auto"},
            **({"minimax": {"tts_model": model}} if provider == "minimax" else {}),
        })
    elif name == "music" and provider == "minimax":
        settings_store.save_settings({"minimax": {"music_model": model}})
    elif name == "stt":
        provider_map = {"auto": "auto", "apple": "apple", "whisper": "whisper", "groq": "groq", "openai": "openai", "deepgram": "deepgram"}
        settings_store.save_settings({"stt": {"provider": provider_map.get(provider, "auto"), "model": model}})


def _safe_workflow_payload(name: str, body: WorkflowBody) -> dict[str, Any]:
    raw = body.model_dump()
    normalized = workflow_config.normalize_workflow(name, raw)
    routes = normalized.get("routes") or []
    if not routes:
        raise HTTPException(400, "Add at least one model route.")
    for route in routes:
        provider = str(route.get("provider") or "")
        model_id = str(route.get("model") or "")
        if provider not in workflow_config.WORKFLOW_PROVIDERS.get(name, ()):
            raise HTTPException(400, f"Provider {provider!r} is not valid for {name}.")
        catalog_entry = catalog.catalog(provider)
        allowed = {str(item.get("id")) for item in catalog_entry.get("models", [])}
        if not allowed:
            raise HTTPException(
                400,
                f"Model catalog for {provider} is unavailable. Refresh catalogs first.",
            )
        if model_id not in allowed:
            raise HTTPException(
                400,
                f"{model_id!r} is not in the current {provider} catalog.",
            )
    return normalized


@router.get("/bootstrap")
def bootstrap_state(request: Request) -> dict:
    needed = store.count_users() == 0
    return {
        "needed": needed,
        "allowed": bool(needed and _local_bootstrap_allowed()),
    }


@router.post("/bootstrap")
def bootstrap(body: BootstrapBody, request: Request, response: Response) -> dict:
    if store.count_users():
        raise HTTPException(409, "An admin already exists; signup is disabled.")
    if not _local_bootstrap_allowed():
        raise HTTPException(403, "Admin bootstrap is only allowed from the local app.")
    try:
        user = store.create_user(body.email, body.password)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    session = store.create_session(
        user["email"], _client_ip(request), str(request.headers.get("user-agent") or "")
    )
    _set_cookie(response, session["token"], request)
    _audit(request, user["email"], "admin.bootstrap", resource_type="admin", resource_id=user["email"])
    return {"ok": True, "email": user["email"], "csrf": session["csrf"], "expires": session["expires"]}


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response) -> dict:
    email = str(body.email or "").strip().lower()
    _check_rate(request, email)
    user = store.get_user(email)
    if not user or not store.verify_password(body.password, str(user.get("password_hash") or "")):
        _record_failure(request, email)
        _audit(
            request, email or "anonymous", "auth.login", resource_type="admin",
            resource_id=email, outcome="failed",
        )
        raise HTTPException(401, "Invalid email or password.")
    session = store.create_session(
        user["email"], _client_ip(request), str(request.headers.get("user-agent") or "")
    )
    _set_cookie(response, session["token"], request)
    _audit(request, user["email"], "auth.login", resource_type="admin", resource_id=user["email"])
    return {"ok": True, "email": user["email"], "csrf": session["csrf"], "expires": session["expires"]}


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    session = _session(request)
    _csrf(request, session)
    store.delete_session(str(request.cookies.get(COOKIE_NAME) or ""))
    _clear_cookie(response)
    _audit(request, session["email"], "auth.logout", resource_type="admin")
    return {"ok": True}


@router.get("/me")
def me(request: Request) -> dict:
    session = _session(request)
    return {
        "email": session["email"],
        "csrf": session["csrf"],
        "expires": session["expires"],
        "bootstrap_needed": store.count_users() == 0,
    }


@router.get("/overview")
def overview(request: Request) -> dict:
    session = _session(request)
    audit = store.list_audit(limit=8)
    pipeline = store.list_pipeline_events(limit=8)
    return {
        "email": session["email"],
        "keys": [_secret_info(name) for name in catalog.AI_SECRETS],
        "workflows": settings_store.load_settings().get("workflows") or {},
        "audit": audit["entries"],
        "pipeline": pipeline["entries"],
    }


@router.get("/keys")
def keys(request: Request) -> dict:
    _session(request)
    return {"keys": [_secret_info(name) for name in catalog.AI_SECRETS]}


@router.post("/keys/{name}")
def save_key(name: str, body: KeyBody, request: Request) -> dict:
    session = _session(request)
    _csrf(request, session)
    name = str(name or "").strip()
    if name not in catalog.AI_SECRETS:
        raise HTTPException(404, "Unknown AI key.")
    before = _secret_info(name)
    try:
        settings_store.save_secrets({name: body.value})
    except OSError as exc:
        raise HTTPException(500, f"Could not save key: {exc}") from exc
    after = _secret_info(name)
    catalog.clear_cache({
        "opencode": "opencode-go", "openrouter": "openrouter", "openai": "openai",
        "groq": "groq", "elevenlabs": "elevenlabs",
    }.get(name, name))
    _audit(
        request, session["email"], "keys.update", resource_type="secret", resource_id=name,
        before=before, after=after,
    )
    return {"ok": True, "key": after}


@router.post("/keys/{name}/test")
def test_key(name: str, request: Request) -> dict:
    session = _session(request)
    _csrf(request, session)
    name = str(name or "").strip()
    if name not in catalog.AI_SECRETS:
        raise HTTPException(404, "Unknown AI key.")
    if not settings_store.get_secret(name):
        result = {"ok": False, "detail": "Key is not configured."}
    elif name in {"opencode", "openrouter"}:
        try:
            import app  # noqa: PLC0415
            result = app.test_settings(app.SettingsTestBody(kind=name))
        except Exception as exc:  # noqa: BLE001
            result = {"ok": False, "detail": f"Test failed: {store.redact_text(exc)}"[:300]}
    else:
        result = {
            "ok": True,
            "detail": "Key is stored. Live provider test is not available for this provider.",
        }
    _audit(
        request, session["email"], "keys.test", resource_type="secret", resource_id=name,
        after={"ok": bool(result.get("ok")), "detail": result.get("detail") or ""},
    )
    return result


@router.get("/catalog")
def get_catalog(
    request: Request,
    provider: str = "",
    workflow: str = "",
    refresh: int = 0,
) -> dict:
    _session(request)
    provider = str(provider or "").strip()
    if provider not in catalog.PROVIDER_META:
        raise HTTPException(400, "Unknown model provider.")
    result = catalog.catalog(provider, refresh=bool(refresh))
    kind = workflow_config.WORKFLOW_KIND.get(workflow)
    if kind in {"text", "tts", "music", "stt"}:
        filtered = [
            item for item in result.get("models", [])
            if not item.get("kind") or item.get("kind") == kind
        ]
        result = {**result, "models": filtered}
    return result


@router.get("/workflows")
def get_workflows(request: Request) -> dict:
    _session(request)
    workflows = settings_store.load_settings().get("workflows") or {}
    return {
        "workflows": workflow_config.normalize_workflows(workflows),
        "labels": workflow_config.WORKFLOW_LABELS,
        "kinds": workflow_config.WORKFLOW_KIND,
        "providers": workflow_config.WORKFLOW_PROVIDERS,
        "provider_meta": catalog.provider_options(),
        "reasoning_values": list(workflow_config.REASONING_VALUES),
    }


@router.post("/workflows/{name}")
def save_workflow(name: str, body: WorkflowBody, request: Request) -> dict:
    session = _session(request)
    _csrf(request, session)
    name = str(name or "").strip()
    if name not in workflow_config.DEFAULT_WORKFLOWS:
        raise HTTPException(404, "Unknown workflow.")
    before = settings_store.load_settings().get("workflows", {}).get(name)
    normalized = _safe_workflow_payload(name, body)
    settings_store.save_settings({"workflows": {name: normalized}})
    _mirror_legacy_workflow(name, normalized)
    after = settings_store.load_settings().get("workflows", {}).get(name)
    try:
        import audio  # noqa: PLC0415
        audio.clear_workflow_caches()
    except Exception:  # noqa: BLE001
        pass
    _audit(
        request, session["email"], "models.update", resource_type="workflow",
        resource_id=name, before=before, after=after,
    )
    return {"ok": True, "workflow": name, "value": after}


@router.post("/workflows/{name}/reset")
def reset_workflow(name: str, request: Request) -> dict:
    session = _session(request)
    _csrf(request, session)
    name = str(name or "").strip()
    if name not in workflow_config.DEFAULT_WORKFLOWS:
        raise HTTPException(404, "Unknown workflow.")
    before = settings_store.load_settings().get("workflows", {}).get(name)
    default = workflow_config.default_workflows()[name]
    settings_store.save_settings({"workflows": {name: default}})
    _mirror_legacy_workflow(name, default)
    try:
        import audio  # noqa: PLC0415
        audio.clear_workflow_caches()
    except Exception:  # noqa: BLE001
        pass
    _audit(
        request, session["email"], "models.reset", resource_type="workflow",
        resource_id=name, before=before, after=default,
    )
    return {"ok": True, "value": default}


@router.get("/audit")
def get_audit(
    request: Request,
    limit: int = 100,
    offset: int = 0,
    actor: str = "",
    action: str = "",
    resource_type: str = "",
) -> dict:
    session = _session(request)
    result = store.list_audit(
        limit=limit, offset=offset, actor=actor, action=action, resource_type=resource_type,
    )
    _audit(request, session["email"], "audit.view", resource_type="audit")
    return result


@router.get("/audit/export")
def export_audit(request: Request) -> Response:
    session = _session(request)
    result = store.list_audit(limit=500, offset=0)
    body = "\n".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) for entry in result["entries"])
    _audit(request, session["email"], "audit.export", resource_type="audit", after={"entries": len(result["entries"])})
    return Response(
        body,
        media_type="application/x-ndjson",
        headers={"Content-Disposition": 'attachment; filename="vibecut-admin-audit.jsonl"'},
    )


@router.get("/audit/verify")
def verify_audit(request: Request) -> dict:
    session = _session(request)
    result = store.verify_audit()
    _audit(
        request, session["email"], "audit.verify", resource_type="audit",
        after=result,
    )
    return result


@router.get("/pipeline")
def get_pipeline(
    request: Request,
    limit: int = 100,
    offset: int = 0,
    workflow: str = "",
    provider: str = "",
    status: str = "",
    job_id: str = "",
) -> dict:
    _session(request)
    return store.list_pipeline_events(
        limit=limit, offset=offset, workflow=workflow, provider=provider,
        status=status, job_id=job_id,
    )


@router.post("/account")
def update_account(body: AccountBody, request: Request, response: Response) -> dict:
    session = _session(request)
    _csrf(request, session)
    user = store.get_user(user_id=session["user_id"])
    if not user or not store.verify_password(body.current_password, str(user.get("password_hash") or "")):
        raise HTTPException(401, "Current password is incorrect.")
    new_email = str(body.email or "").strip().lower()
    if new_email != user["email"] and store.get_user(new_email):
        raise HTTPException(409, "That admin email is already in use.")
    new_password = str(body.new_password or "")
    if new_password and len(new_password) < 12:
        raise HTTPException(400, "New password must be at least 12 characters.")
    before = {"email": user["email"], "password": "changed" if new_password else "unchanged"}
    try:
        updated = store.update_user(new_email, new_password or None)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    store.delete_other_sessions(int(updated["id"]), keep_hash=session["token_hash"])
    after = {"email": updated["email"], "password": "changed" if new_password else "unchanged"}
    _audit(
        request, updated["email"], "account.update", resource_type="admin",
        resource_id=updated["email"], before=before, after=after,
    )
    return {"ok": True, "email": updated["email"], "csrf": session["csrf"]}
