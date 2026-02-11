"""
ESPHomeCLI AddOn - Web API for ESPHome CLI.
Async job-based: validate, compile, upload, run, clean.
Pasted YAML only (no storage); temp files under DATA_DIR.
"""
import asyncio
import json
import logging
import os
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any, Optional

from starlette.exceptions import NotFound

from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Log to stdout so it appears in addon logs (HA: Add-on → Log)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# Addon data dir (mapped volume)
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
WORKSPACE = DATA_DIR / "workspace"
OPTIONS_PATH = DATA_DIR / "options.json"

# In-memory job store: job_id -> { type, status, logs, result, error, created_at }
jobs: dict[str, dict[str, Any]] = {}
jobs_lock = threading.Lock()

# Allowed esphome subcommands (no arbitrary commands)
ALLOWED_COMMANDS = {"config", "compile", "upload", "run", "clean"}

app = FastAPI(title="ESPHome CLI API", version="1.0.0")

# Load UI HTML once so middleware can serve it for root/// (Ingress sends GET //)
STATIC_DIR = Path(__file__).parent / "static"
INDEX_HTML = (STATIC_DIR / "index.html").read_text(encoding="utf-8") if (STATIC_DIR / "index.html").exists() else "<!DOCTYPE html><html><body><h1>UI not found</h1></body></html>"


@app.exception_handler(NotFound)
async def custom_not_found(request: Request, exc: NotFound):
    """If no route matched and path is root (e.g. GET // from Ingress), serve UI so panel loads."""
    if request.method == "GET" and request.url.path in ("//", "/", ""):
        log.info("NotFound fallback: serving UI for path %r", request.url.path)
        return HTMLResponse(INDEX_HTML)
    from starlette.responses import JSONResponse
    return JSONResponse(status_code=404, content={"detail": "Not found"})


@app.on_event("startup")
async def startup():
    log.info("ESPHome CLI addon starting; DATA_DIR=%s", DATA_DIR)
    log.info("UI routes: GET / , GET /api/hassio_ingress/{path} , GET /{path} (catch-all)")


@app.middleware("http")
async def normalize_path_and_log(request: Request, call_next):
    """Normalize path (e.g. // -> /) and log. Ingress can send // which 404s otherwise."""
    method = request.method
    raw_path = request.url.path
    scope_path = request.scope.get("path", "<missing>")
    is_root = method == "GET" and raw_path in ("//", "/", "")
    # Log every request so we can see what actually reaches the app (path repr, bytes, scope)
    log.info(
        "DIAG %s raw_path=%r (len=%d) scope_path=%r is_root=%s",
        method, raw_path, len(raw_path), scope_path, is_root,
    )
    if is_root:
        log.info("Serving UI for root (raw_path=%r)", raw_path)
        return HTMLResponse(INDEX_HTML)
    path = raw_path
    while "//" in path:
        path = path.replace("//", "/")
    if path != raw_path:
        request.scope["path"] = path
        request.scope["raw_path"] = path.encode("utf-8")
    path = request.scope["path"]
    headers = dict(request.headers)
    ingress_related = {
        k: headers.get(k)
        for k in (
            "x-ingress-path",
            "x-forwarded-for",
            "x-forwarded-host",
            "x-forwarded-proto",
            "x-forwarded-uri",
            "x-request-uri",
            "x-original-uri",
        )
        if headers.get(k)
    }
    log.info("Request: %s %s | ingress-related: %s", method, path, ingress_related or "none")
    try:
        response = await call_next(request)
        log.info("Response: %s %s -> %s", method, path, response.status_code)
        return response
    except Exception as e:
        log.exception("Request failed: %s %s -> %s", method, path, e)
        raise


# --- Options (addon config) ---
def get_options() -> dict:
    if not OPTIONS_PATH.exists():
        return {}
    try:
        return json.loads(OPTIONS_PATH.read_text())
    except Exception:
        return {}


# --- Auth: validate Bearer token with HA (when auth_api enabled) ---
async def verify_ha_token(authorization: Optional[str] = Header(None)) -> bool:
    """If addon has auth_api, we can validate token via Supervisor. For Ingress, HA already authenticated."""
    # Ingress requests come with session; direct API calls may send Bearer token.
    if not authorization or not authorization.startswith("Bearer "):
        return False
    token = authorization.replace("Bearer ", "").strip()
    if not token:
        return False
    # Call Supervisor proxy to HA: GET /api/ with Authorization
    import urllib.request
    req = urllib.request.Request(
        "http://supervisor/core/api/",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


async def optional_auth(request: Request, authorization: Optional[str] = Header(None)) -> None:
    """Allow request if: from Ingress (has X-Ingress-Path or trusted), or Bearer valid."""
    # When loaded via Ingress, request is already authenticated by HA
    if request.headers.get("X-Ingress-Path") or request.headers.get("X-Hass-Source"):
        return
    if authorization and authorization.startswith("Bearer "):
        if await verify_ha_token(authorization):
            return
    # Allow unauthenticated for health and for simpler local use; tighten in production
    # raise HTTPException(status_code=401, detail="Not authorized")
    return


# --- Request/response models ---
class YamlBody(BaseModel):
    yaml: str = Field(..., description="ESPHome YAML configuration content")


class ValidateRequest(BaseModel):
    yaml: str = Field(..., description="ESPHome YAML configuration content")


class CompileRequest(BaseModel):
    yaml: str = Field(..., description="ESPHome YAML configuration content")
    substitutions: Optional[dict[str, str]] = None
    only_generate: bool = False


class UploadRequest(BaseModel):
    yaml: str = Field(..., description="ESPHome YAML configuration content")
    device: Optional[str] = Field(None, description="Upload port or IP, e.g. 192.168.1.10 or /dev/ttyUSB0")
    upload_speed: Optional[int] = None
    substitutions: Optional[dict[str, str]] = None


class RunRequest(BaseModel):
    yaml: str = Field(..., description="ESPHome YAML configuration content")
    device: Optional[str] = None
    upload_speed: Optional[int] = None
    no_logs: bool = False
    substitutions: Optional[dict[str, str]] = None


class CleanRequest(BaseModel):
    yaml: str = Field(..., description="ESPHome YAML configuration content")


# --- Helpers: temp file and esphome subprocess ---
def ensure_workspace() -> Path:
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    return WORKSPACE


def write_temp_yaml(content: str, job_id: str) -> Path:
    ws = ensure_workspace()
    path = ws / f"config_{job_id}.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def build_esphome_args(
    subcommand: str,
    config_path: Path,
    *,
    device: Optional[str] = None,
    upload_speed: Optional[int] = None,
    only_generate: bool = False,
    no_logs: bool = False,
    substitutions: Optional[dict[str, str]] = None,
) -> list[str]:
    if subcommand not in ALLOWED_COMMANDS:
        raise ValueError(f"Command not allowed: {subcommand}")
    args = ["esphome", subcommand, str(config_path)]
    if subcommand == "compile" and only_generate:
        args.append("--only-generate")
    if device and subcommand in ("upload", "run"):
        args.extend(["--device", device])
    if upload_speed and subcommand in ("upload", "run"):
        args.extend(["--upload-speed", str(upload_speed)])
    if no_logs and subcommand == "run":
        args.append("--no-logs")
    if substitutions:
        for k, v in substitutions.items():
            args.extend(["--substitution", k, str(v)])
    return args


def run_esphome_sync(args: list[str], job_id: str) -> tuple[int, str, str]:
    """Run esphome, capture stdout/stderr, update job logs. Returns (returncode, stdout, stderr)."""
    config_path = Path(args[-1])
    cwd = str(config_path.parent) if config_path.is_file() else str(WORKSPACE)
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id]["status"] = "running"
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=600,
            cwd=cwd,
        )
        stdout, stderr = proc.stdout or "", proc.stderr or ""
        with jobs_lock:
            if job_id in jobs:
                jobs[job_id]["logs"] = (jobs[job_id].get("logs") or "") + stdout + stderr
                jobs[job_id]["status"] = "success" if proc.returncode == 0 else "failed"
                jobs[job_id]["returncode"] = proc.returncode
                if proc.returncode != 0:
                    jobs[job_id]["error"] = stderr or stdout or f"Exit code {proc.returncode}"
        return proc.returncode, stdout, stderr
    except subprocess.TimeoutExpired:
        with jobs_lock:
            if job_id in jobs:
                jobs[job_id]["status"] = "failed"
                jobs[job_id]["error"] = "Command timed out (600s)"
        return -1, "", "Timeout"
    except Exception as e:
        with jobs_lock:
            if job_id in jobs:
                jobs[job_id]["status"] = "failed"
                jobs[job_id]["error"] = str(e)
        raise


def run_job(job_id: str, job_type: str, args: list[str], config_path: Path) -> None:
    """Background thread target: run esphome and optionally delete temp file."""
    try:
        run_esphome_sync(args, job_id)
    finally:
        try:
            config_path.unlink(missing_ok=True)
        except Exception:
            pass


# --- Sync validate (quick) ---
@app.post("/api/validate")
async def api_validate(body: ValidateRequest):
    """Validate pasted YAML (synchronous). Returns validation result."""
    job_id = str(uuid.uuid4())
    config_path = write_temp_yaml(body.yaml, job_id)
    try:
        args = build_esphome_args("config", config_path)
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(config_path.parent),
        )
        stdout, stderr = (proc.stdout or ""), (proc.stderr or "")
        config_path.unlink(missing_ok=True)
        if proc.returncode != 0:
            return {
                "valid": False,
                "error": stderr or stdout or f"Exit code {proc.returncode}",
                "stdout": stdout,
                "stderr": stderr,
            }
        return {"valid": True, "stdout": stdout, "stderr": stderr}
    except subprocess.TimeoutExpired:
        config_path.unlink(missing_ok=True)
        raise HTTPException(status_code=408, detail="Validation timed out")
    except Exception as e:
        config_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=str(e))


# --- Async job endpoints ---
@app.post("/api/compile")
async def api_compile(body: CompileRequest):
    job_id = str(uuid.uuid4())
    config_path = write_temp_yaml(body.yaml, job_id)
    args = build_esphome_args(
        "compile",
        config_path,
        only_generate=body.only_generate,
        substitutions=body.substitutions,
    )
    with jobs_lock:
        jobs[job_id] = {
            "type": "compile",
            "status": "pending",
            "logs": "",
            "error": None,
            "created_at": asyncio.get_event_loop().time(),
        }
    threading.Thread(target=run_job, args=(job_id, "compile", args, config_path), daemon=True).start()
    return {"job_id": job_id}


@app.post("/api/upload")
async def api_upload(body: UploadRequest):
    job_id = str(uuid.uuid4())
    config_path = write_temp_yaml(body.yaml, job_id)
    args = build_esphome_args(
        "upload",
        config_path,
        device=body.device,
        upload_speed=body.upload_speed,
        substitutions=body.substitutions,
    )
    with jobs_lock:
        jobs[job_id] = {
            "type": "upload",
            "status": "pending",
            "logs": "",
            "error": None,
            "created_at": asyncio.get_event_loop().time(),
        }
    threading.Thread(target=run_job, args=(job_id, "upload", args, config_path), daemon=True).start()
    return {"job_id": job_id}


@app.post("/api/run")
async def api_run(body: RunRequest):
    job_id = str(uuid.uuid4())
    config_path = write_temp_yaml(body.yaml, job_id)
    args = build_esphome_args(
        "run",
        config_path,
        device=body.device,
        upload_speed=body.upload_speed,
        no_logs=body.no_logs,
        substitutions=body.substitutions,
    )
    with jobs_lock:
        jobs[job_id] = {
            "type": "run",
            "status": "pending",
            "logs": "",
            "error": None,
            "created_at": asyncio.get_event_loop().time(),
        }
    threading.Thread(target=run_job, args=(job_id, "run", args, config_path), daemon=True).start()
    return {"job_id": job_id}


@app.post("/api/clean")
async def api_clean(body: CleanRequest):
    job_id = str(uuid.uuid4())
    config_path = write_temp_yaml(body.yaml, job_id)
    args = build_esphome_args("clean", config_path)
    with jobs_lock:
        jobs[job_id] = {
            "type": "clean",
            "status": "pending",
            "logs": "",
            "error": None,
            "created_at": asyncio.get_event_loop().time(),
        }
    threading.Thread(target=run_job, args=(job_id, "clean", args, config_path), daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/jobs")
async def api_list_jobs():
    with jobs_lock:
        return {"jobs": [{"job_id": jid, **{k: v for k, v in data.items() if k != "logs"}} for jid, data in list(jobs.items())]}


@app.get("/api/jobs/{job_id}")
async def api_get_job(job_id: str):
    with jobs_lock:
        if job_id not in jobs:
            raise HTTPException(status_code=404, detail="Job not found")
        return jobs[job_id]


@app.get("/api/health")
async def api_health():
    return {"status": "ok"}


# --- Serve UI (Ingress) ---
# STATIC_DIR and INDEX_HTML defined at top for middleware root/ // handling
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def root():
    log.info("Serving UI at /")
    return HTMLResponse(INDEX_HTML)


# Ingress often sends GET // (double slash); FastAPI matches path exactly so add explicit route
@app.get("//", response_class=HTMLResponse)
async def root_double_slash():
    log.info("Serving UI at //")
    return HTMLResponse(INDEX_HTML)


@app.get("/api/hassio_ingress/{rest:path}", response_class=HTMLResponse)
async def ingress_ui(rest: str):
    """Serve UI when request comes through Ingress (path prefix from Supervisor)."""
    log.info("Serving UI at /api/hassio_ingress/%s", rest)
    return HTMLResponse(INDEX_HTML)


# Catch-all for any other GET (log and serve UI so we can see what path was requested)
@app.api_route("/{full_path:path}", methods=["GET"], response_class=HTMLResponse)
async def catch_all_ui(request: Request, full_path: str):
    """Serve UI for any unhandled GET (helps diagnose 404s)."""
    log.warning("Catch-all GET for path: %r (full_path=%r) - serving UI", request.url.path, full_path)
    return HTMLResponse(INDEX_HTML)
