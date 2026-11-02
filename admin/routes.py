"""Password-only admin console routes under ``/_ductator``."""

from __future__ import annotations

import ipaddress
import json
import threading
import time
import urllib.parse
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

import settings_store
import workflow_config
from admin import catalog, store

router = APIRouter(prefix="/_ductator/api", tags=["admin"])
COOKIE_NAME = "vibecut_admin"
COOKIE_PATH = "/_ductator"
CSRF_HEADER = "X-VibeCut-Admin-CSRF"

_LOCK = threading.Lock()
_ATTEMPTS: dict[str, list[float]] = {}
MAX_EMAIL_ATTEMPTS = 8
MAX_IP_ATTEMPTS = 30
ATTEMPT_WINDOW = 15 * 60
MAX_RATE_KEYS = 2048
MAX_EMAIL_LENGTH = 320
MAX_PASSWORD_LENGTH = 1024
MAX_KEY_LENGTH = 8192
MAX_ROUTE_MODEL_LENGTH = 240


def _active_ai_secrets() -> tuple[str, ...]:
    """AI keys that still belong to a shipped engine.

    OpenAI TTS/STT and Cartesia TTS are gone; their old keys stay readable for
    legacy jobs but are hidden from the masked-key list until the creator
    confirms deletion.
    """
    stale = set(settings_store.STALE_SECRETS)
    return tuple(name for name in catalog.AI_SECRETS if name not in stale)


def _admin_providers() -> set[str]:
    return {
        str(provider)
        for providers in workflow_config.WORKFLOW_PROVIDERS.values()
        for provider in providers
    }


class BootstrapBody(BaseModel):
    password: str = Field(min_length=12, max_length=MAX_PASSWORD_LENGTH)


class LoginBody(BaseModel):
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class AccountBody(BaseModel):
    current_password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)
    new_password: str = Field(default="", max_length=MAX_PASSWORD_LENGTH)


class KeyBody(BaseModel):
    value: str = Field(default="", max_length=MAX_KEY_LENGTH)
    clear: bool = False


class WorkflowBody(BaseModel):
    routes: list[dict] = Field(default_factory=list)
    reasoning: str = Field(default="", max_length=32)
    max_output_tokens: int = 3200
    timeout_s: int = 300


class ConfirmRemovalsBody(BaseModel):
    confirm: bool = False


def _client_ip(request: Request) -> str:
    return str(getattr(request.client, "host", "") or "")


def _hostname(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "://" in text:
        try:
            parsed = urllib.parse.urlsplit(text)
        except ValueError:
            return ""
        return str(parsed.hostname or "").lower()
    if text.startswith("["):
        end = text.find("]")
        return text[1:end].lower() if end > 0 else ""
    return text.split(":", 1)[0].strip().lower()


def _is_loopback_host(value: str) -> bool:
    host = _hostname(value)
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _local_bootstrap_allowed(request: Request) -> bool:
    """Allow bootstrap only for a genuinely local, non-proxied request."""
    if not _is_loopback_host(_client_ip(request)):
        return False
    if not _is_loopback_host(str(request.headers.get("host") or "")):
        return False
    origin = str(request.headers.get("origin") or "")
    if origin and not _is_loopback_host(origin):
        return False
    for header in (
        "forwarded", "x-forwarded-for", "x-forwarded-host", "x-real-ip",
        "cf-connecting-ip",
    ):
        if request.headers.get(header):
            return False
    try:
        import app  # noqa: PLC0415
        if not _is_loopback_host(str(app.HOST)):
            return False
    except Exception:  # noqa: BLE001
        return False
    return True


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


def _bucket_keys(request: Request, email: str) -> list[tuple[str, int]]:
    ip = _client_ip(request) or "unknown"
    email = str(email or "").strip().lower()[:MAX_EMAIL_LENGTH]
    return [
        (f"ip:{ip}", MAX_IP_ATTEMPTS),
        (f"email:{email or 'empty'}", MAX_EMAIL_ATTEMPTS),
    ]


def _prune_attempts(now: float) -> None:
    for key in list(_ATTEMPTS):
        attempts = [item for item in _ATTEMPTS.get(key, []) if now - item < ATTEMPT_WINDOW]
        if attempts:
            _ATTEMPTS[key] = attempts
        else:
            _ATTEMPTS.pop(key, None)
    if len(_ATTEMPTS) > MAX_RATE_KEYS:
        oldest = sorted(
            _ATTEMPTS, key=lambda key: max(_ATTEMPTS.get(key) or [0.0]),
        )[: max(0, len(_ATTEMPTS) - MAX_RATE_KEYS)]
        for key in oldest:
            _ATTEMPTS.pop(key, None)


def _check_rate(request: Request, email: str) -> None:
    now = time.time()
    with _LOCK:
        _prune_attempts(now)
        for key, limit in _bucket_keys(request, email):
            if len(_ATTEMPTS.get(key, [])) >= limit:
                raise HTTPException(429, "Too many login attempts. Try again later.")


def _record_failure(request: Request, email: str) -> None:
    now = time.time()
    with _LOCK:
        _prune_attempts(now)
        for key, _limit in _bucket_keys(request, email):
            _ATTEMPTS.setdefault(key, []).append(now)


def _set_cookie(response: Response, token: str, request: Request) -> None:
    forwarded = str(request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=store.SESSION_HOURS * 3600,
        path=COOKIE_PATH,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https" or forwarded == "https",
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
            tts_provider = (
                "heygen" if "heygen" in model.lower()
                else "fish" if "fish" in model.lower() else "gemini"
            )
        elif provider == "local":
            tts_provider = model if model in {"kokoro", "say"} else "kokoro"
        settings_store.save_settings({
            "tts": {"provider": tts_provider if tts_provider in {
                "minimax", "heygen", "fish", "gemini", "kokoro", "say", "local", "auto",
                "elevenlabs",
            } else "auto"},
            **({"minimax": {"tts_model": model}} if provider == "minimax" else {}),
        })
    elif name == "music" and provider == "minimax":
        settings_store.save_settings({"minimax": {"music_model": model}})
    elif name in {"rewrite", "translate", "story_brief", "hook_rank", "script"}:
        reasoning = str(normalized.get("reasoning") or "low")
        if provider == "opencode-go":
            settings_store.save_settings({
                "opencode": {"model": model, "variant": reasoning},
            })
        elif provider == "openrouter":
            settings_store.save_settings({
                "openrouter": {"model": model, "reasoning": reasoning},
            })
    elif name == "stt":
        provider_map = {
            "apple": "apple", "whisper": "whisper",
            "groq": "groq", "deepgram": "deepgram",
            "openrouter": "openrouter",
        }
        legacy = {"provider": provider_map.get(provider, "apple")}
        # The legacy Setup field only lists Whisper model IDs. Apple is a
        # route provider, not a Whisper model, so leave the old model intact.
        if provider != "apple":
            legacy["model"] = model
        settings_store.save_settings({"stt": legacy})


def _model_kind(provider: str, item: dict[str, Any]) -> str:
    kind = str(item.get("kind") or "").strip().lower()
    if kind in {"text", "tts", "music", "stt"}:
        return kind
    return "tts" if provider == "local" else "text"


def _safe_workflow_payload(name: str, body: WorkflowBody) -> dict[str, Any]:
    kind = workflow_config.WORKFLOW_KIND.get(name, "text")
    raw_routes = body.routes
    if not isinstance(raw_routes, list) or not raw_routes:
        raise HTTPException(400, "Add at least one model route.")
    if len(raw_routes) > workflow_config.MAX_ROUTES:
        raise HTTPException(400, f"At most {workflow_config.MAX_ROUTES} model routes are allowed.")
    checked: list[dict[str, str]] = []
    for item in raw_routes:
        if not isinstance(item, dict):
            raise HTTPException(400, "Every model route must be an object.")
        provider = str(item.get("provider") or "").strip().lower()
        model_id = str(item.get("model") or "").strip()
        if provider not in workflow_config.WORKFLOW_PROVIDERS.get(name, ()):
            raise HTTPException(400, f"Provider {provider!r} is not valid for {name}.")
        if not model_id or len(model_id) > MAX_ROUTE_MODEL_LENGTH:
            raise HTTPException(400, "Every model route needs a valid model id.")
        if (
            name == "tts"
            and provider == "local"
            and model_id in workflow_config.REMOVED_TTS_MODELS
        ):
            raise HTTPException(400, "Piper was removed. Use Kokoro or Apple say.")
        catalog_entry = catalog.catalog(provider)
        models = catalog_entry.get("models") if isinstance(catalog_entry, dict) else []
        allowed = {
            str(entry.get("id"))
            for entry in (models or [])
            if isinstance(entry, dict)
            and entry.get("id")
            and _model_kind(provider, entry) == kind
        }
        if not allowed:
            raise HTTPException(
                400,
                f"No {kind} models are available for {provider}. Refresh catalogs first.",
            )
        if model_id not in allowed:
            raise HTTPException(
                400,
                f"{model_id!r} is not a {kind} model in the current {provider} catalog.",
            )
        checked.append({"provider": provider, "model": model_id})
    normalized = workflow_config.normalize_workflow(name, body.model_dump())
    normalized["routes"] = checked
    return normalized



@router.get("/bootstrap")
def bootstrap_state(request: Request) -> dict:
    needed = store.count_users() == 0
    return {
        "needed": needed,
        "allowed": bool(needed and _local_bootstrap_allowed(request)),
    }


@router.post("/bootstrap")
def bootstrap(body: BootstrapBody, request: Request, response: Response) -> dict:
    if store.count_users():
        raise HTTPException(409, "An admin already exists; signup is disabled.")
    if not _local_bootstrap_allowed(request):
        raise HTTPException(403, "Admin bootstrap is only allowed from a direct local request.")
    try:
        user = store.create_user(body.password)
    except ValueError as exc:
        raise HTTPException(409 if "already exists" in str(exc) else 400, str(exc)) from exc
    session = store.create_session(
        user["email"], _client_ip(request), str(request.headers.get("user-agent") or "")
    )
    _set_cookie(response, session["token"], request)
    _audit(request, user["email"], "admin.bootstrap", resource_type="admin", resource_id=user["email"])
    return {"ok": True, "account": user["email"], "csrf": session["csrf"], "expires": session["expires"]}


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response) -> dict:
    account = store.ADMIN_ACCOUNT
    _check_rate(request, account)
    user = store.first_user()
    if not user or not store.verify_password(body.password, str(user.get("password_hash") or "")):
        _record_failure(request, account)
        _audit(
            request, "anonymous", "auth.login", resource_type="admin",
            resource_id=account, outcome="failed",
        )
        raise HTTPException(401, "Invalid password.")
    session = store.create_session(
        user["email"], _client_ip(request), str(request.headers.get("user-agent") or "")
    )
    _set_cookie(response, session["token"], request)
    _audit(request, user["email"], "auth.login", resource_type="admin", resource_id=user["email"])
    return {"ok": True, "account": user["email"], "csrf": session["csrf"], "expires": session["expires"]}


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
        "account": session["email"],
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
        "account": session["email"],
        "keys": [_secret_info(name) for name in _active_ai_secrets()],
        "stale_secrets": settings_store.stale_secret_status(),
        "workflows": settings_store.load_settings().get("workflows") or {},
        "audit": audit["entries"],
        "pipeline": pipeline["entries"],
    }


@router.get("/keys")
def keys(request: Request) -> dict:
    _session(request)
    return {
        "keys": [_secret_info(name) for name in _active_ai_secrets()],
        "stale_secrets": settings_store.stale_secret_status(),
        "paths": {
            "settings": str(settings_store.SETTINGS_PATH),
            "secrets": str(settings_store.SECRETS_PATH),
        },
    }


@router.post("/keys/confirm-removals")
def confirm_key_removals(body: ConfirmRemovalsBody, request: Request) -> dict:
    session = _session(request)
    _csrf(request, session)
    if not body.confirm:
        raise HTTPException(400, "Confirm deletion of removed-engine keys.")
    before = settings_store.stale_secret_status()
    result = settings_store.confirm_stale_secrets()
    _audit(
        request, session["email"], "keys.remove_removed_engines",
        resource_type="secret", before=before, after=result,
    )
    return {"ok": True, **result}


def _clear_key_runtime(name: str) -> None:
    """Clear quarantine, breakers, and catalog/cache state after key rotation."""
    try:
        import audio  # noqa: PLC0415
        provider = {
            "opencode": "opencode-go", "openrouter": "openrouter",
            "groq": "groq", "elevenlabs": "elevenlabs", "minimax": "minimax",
            "deepgram": "deepgram",
        }.get(name, name)
        audio.clear_openrouter_quarantine()
        audio.reset_provider_breaker(provider)
        audio.OPENROUTER_LAST_ERROR = ""
        audio.OPENROUTER_LAST_STATUS = 0
        audio.clear_workflow_caches()
    except Exception:  # noqa: BLE001
        pass
    try:
        catalog.clear_cache({
            "opencode": "opencode-go", "openrouter": "openrouter",
            "groq": "groq", "elevenlabs": "elevenlabs",
        }.get(name, name))
    except Exception:  # noqa: BLE001
        pass


@router.post("/keys/{name}")
def save_key(name: str, body: KeyBody, request: Request) -> dict:
    session = _session(request)
    _csrf(request, session)
    name = str(name or "").strip()
    if name not in _active_ai_secrets():
        raise HTTPException(404, "Unknown AI key.")
    before = _secret_info(name)
    if settings_store.secret_source(name) == "env":
        raise HTTPException(
            409,
            f"{before['label']} is managed by {before.get('env') or 'the environment'}; "
            "change or unset that environment variable to rotate it.",
        )
    if not body.clear and not str(body.value or "").strip():
        raise HTTPException(400, "Enter a key before saving. Use Clear to remove it.")
    try:
        settings_store.save_secrets({name: "" if body.clear else body.value})
    except OSError as exc:
        raise HTTPException(500, f"Could not save key: {store.redact_text(exc)}") from exc
    after = _secret_info(name)
    _clear_key_runtime(name)
    _audit(
        request, session["email"], "keys.update", resource_type="secret", resource_id=name,
        before=before, after=after,
        detail="cleared" if body.clear else "stored",
    )
    return {"ok": True, "key": after}


@router.post("/keys/{name}/test")
def test_key(name: str, request: Request) -> dict:
    session = _session(request)
    _csrf(request, session)
    name = str(name or "").strip()
    if name not in _active_ai_secrets():
        raise HTTPException(404, "Unknown AI key.")
    if not settings_store.get_secret(name):
        result = {"ok": False, "tested": False, "detail": "Key is not configured."}
    elif name in {"opencode", "openrouter"}:
        try:
            import app  # noqa: PLC0415
            result = app.test_settings(app.SettingsTestBody(kind=name))
        except Exception as exc:  # noqa: BLE001
            result = {
                "ok": False, "tested": True,
                "detail": f"Test failed: {store.redact_text(exc)}"[:300],
            }
    else:
        result = {
            "ok": True,
            "tested": False,
            "detail": "Stored (not tested). This provider has no live key check in the admin console.",
        }
    _audit(
        request, session["email"], "keys.test", resource_type="secret", resource_id=name,
        outcome="ok" if result.get("ok") else "failed",
        after={
            "ok": bool(result.get("ok")), "tested": bool(result.get("tested")),
            "detail": result.get("detail") or "",
        },
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
    if provider not in _admin_providers():
        raise HTTPException(400, "Provider was removed from this workflow.")
    result = catalog.catalog(provider, refresh=bool(refresh))
    kind = workflow_config.WORKFLOW_KIND.get(workflow)
    if kind in {"text", "tts", "music", "stt"}:
        filtered = [
            item for item in result.get("models", [])
            if _model_kind(provider, item) == kind
        ]
        if kind == "tts" and provider == "local":
            filtered = [
                item for item in filtered
                if str(item.get("id") or "") not in workflow_config.REMOVED_TTS_MODELS
            ]
        result = {**result, "models": filtered}
    return result



@router.get("/workflows")
def get_workflows(request: Request) -> dict:
    _session(request)
    workflows = settings_store.load_settings().get("workflows") or {}
    providers = _admin_providers()
    return {
        "workflows": workflow_config.normalize_workflows(workflows),
        "labels": workflow_config.WORKFLOW_LABELS,
        "kinds": workflow_config.WORKFLOW_KIND,
        "providers": workflow_config.WORKFLOW_PROVIDERS,
        "provider_meta": [
            item for item in catalog.provider_options()
            if item.get("id") in providers
        ],
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
    include_http: int = 0,
) -> dict:
    session = _session(request)
    result = store.list_audit(
        limit=limit, offset=offset, actor=actor, action=action, resource_type=resource_type,
        include_http=bool(include_http),
    )
    _audit(request, session["email"], "audit.view", resource_type="audit")
    return result


@router.get("/audit/export")
def export_audit(request: Request) -> Response:
    session = _session(request)
    entries: list[dict] = []
    offset = 0
    while True:
        page = store.list_audit(limit=500, offset=offset, include_http=True)
        entries.extend(page["entries"])
        offset += len(page["entries"])
        if offset >= int(page["total"]) or not page["entries"]:
            break
    body = "\n".join(json.dumps(entry, ensure_ascii=False, sort_keys=True) for entry in entries)
    _audit(
        request, session["email"], "audit.export", resource_type="audit",
        after={"entries": len(entries)},
    )
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
        outcome="ok" if result.get("ok") else "failed",
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
    new_password = str(body.new_password or "")
    if new_password and len(new_password) < 12:
        raise HTTPException(400, "New password must be at least 12 characters.")
    before = {"password": "unchanged"}
    try:
        updated = store.update_user(new_password or None)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    store.delete_other_sessions(int(updated["id"]), keep_hash=session["token_hash"])
    after = {"password": "changed" if new_password else "unchanged"}
    _audit(
        request, updated["email"], "account.update", resource_type="admin",
        resource_id=updated["email"], before=before, after=after,
    )
    return {"ok": True, "account": updated["email"], "csrf": session["csrf"]}