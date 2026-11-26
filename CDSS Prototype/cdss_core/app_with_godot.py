
import hashlib
import os
import secrets
import subprocess
import time
from http.cookies import SimpleCookie
from pathlib import Path
from knowledge_base import load_knowledge, load_media
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from urllib.error import HTTPError, URLError
from urllib.parse import quote
import smart_launch as smart


app: FastAPI = smart.app

LAUNCH_LIFETIME = 90
DESKTOP_HEADER = "x-cdss-desktop-session"

# No new clinical data store.
# These records only associate desktop processes
# with existing SMART sessions.
pending_launches = {}
desktop_credentials = {}
launched_processes = {}


class BootstrapPayload(BaseModel):
    code: str


def hash_secret(value: str) -> str:
    return hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()


def require_local(request: Request) -> None:
    client = request.client

    if (
        client is None
        or client.host not in ("127.0.0.1", "::1")
        or request.url.hostname not in (
            "127.0.0.1", "localhost", "::1"
        )
    ):
        raise HTTPException(
            status_code=403,
            detail="Local CDSS connection required",
        )


def prune_state() -> None:
    smart.clear_expired()
    now = time.time()

    for key, value in list(pending_launches.items()):
        if now >= value["expires"]:
            del pending_launches[key]

    for key, value in list(desktop_credentials.items()):
        if (
            now >= value["expires"]
            or value["session_id"] not in smart.active_sessions
        ):
            del desktop_credentials[key]

    for session_id, process in list(
        launched_processes.items()
    ):
        if (
            session_id not in smart.active_sessions
            or process.poll() is not None
        ):
            del launched_processes[session_id]


def launch_godot(session_id: str) -> None:
    session = smart.active_sessions.get(session_id)

    if session is None:
        return

    existing = launched_processes.get(session_id)

    if existing is not None and existing.poll() is None:
        return

    executable_setting = os.environ.get(
        "CDSS_GODOT_EXECUTABLE"
    )
    project_setting = os.environ.get(
        "CDSS_GODOT_PROJECT"
    )

    if not executable_setting or not project_setting:
        print(
            "Godot launch configuration is missing.",
            flush=True,
        )
        return

    executable = Path(executable_setting)
    project = Path(project_setting)

    if not executable.is_file():
        print(
            f"Godot executable not found: {executable}",
            flush=True,
        )
        return

    if not (project / "project.godot").is_file():
        print(
            f"Godot project not found: {project}",
            flush=True,
        )
        return

    code = secrets.token_urlsafe(32)
    code_key = hash_secret(code)

    pending_launches[code_key] = {
        "session_id": session_id,
        "expires": min(
            time.time() + LAUNCH_LIFETIME,
            session["expires_at"],
        ),
    }

    try:
        process = subprocess.Popen(
            [
                str(executable),
                "--path",
                str(project),
                "--",
                "--cdss-launch=" + code,
            ],
            cwd=str(project),
        )
    except OSError as error:
        pending_launches.pop(code_key, None)
        print(
            f"Godot process could not start: {error}",
            flush=True,
        )
        return

    launched_processes[session_id] = process

    print(
        f"Godot process started: PID {process.pid}",
        flush=True,
    )


def resolve_desktop_session(request: Request):
    require_local(request)
    prune_state()

    token = request.headers.get(DESKTOP_HEADER)

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Desktop credential required",
        )

    entry = desktop_credentials.get(
        hash_secret(token)
    )

    if entry is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid desktop credential",
        )

    session = smart.active_sessions.get(
        entry["session_id"]
    )

    if (
        session is None
        or time.time() >= entry["expires"]
    ):
        raise HTTPException(
            status_code=401,
            detail="Desktop session expired",
        )

    return entry["session_id"], session


@app.middleware("http")
async def desktop_session_middleware(
    request: Request,
    call_next,
):
    prune_state()

    desktop_token = request.headers.get(DESKTOP_HEADER)

    # Only existing case/session APIs may use the
    # desktop credential. Browser OAuth and launch
    # routes retain their original behavior.
    if desktop_token is not None:
        if not request.url.path.startswith("/api/"):
            return JSONResponse(
                {"detail": "Desktop API access only"},
                status_code=403,
            )

        try:
            session_id, _session = resolve_desktop_session(
                request
            )
        except HTTPException as error:
            return JSONResponse(
                {"detail": error.detail},
                status_code=error.status_code,
            )

        # Authenticate against the original SMART
        # session without modifying smart_launch.py.
        original_headers = request.scope["headers"]

        replacement_headers = [
            (key, value)
            for key, value in original_headers
            if key.lower() != b"cookie"
        ]

        replacement_headers.append(
            (
                b"cookie",
                (
                    smart.SESSION_COOKIE
                    + "=" + session_id
                ).encode("ascii"),
            )
        )

        request.scope["headers"] = replacement_headers

    response = await call_next(request)

    # A successful SMART callback is the authoritative
    # launch event in the existing application.
    if (
        request.method == "GET"
        and request.url.path == "/callback"
        and response.status_code == 303
    ):
        cookie_header = response.headers.get(
            "set-cookie", ""
        )

        cookies = SimpleCookie()
        cookies.load(cookie_header)

        session_cookie = cookies.get(
            smart.SESSION_COOKIE
        )

        if session_cookie is not None:
            session_id = session_cookie.value

            if session_id in smart.active_sessions:
                launch_godot(session_id)

    return response


@app.post("/api/desktop/bootstrap")
def desktop_bootstrap(
    payload: BootstrapPayload,
    request: Request,
):
    require_local(request)
    prune_state()

    code_key = hash_secret(payload.code)
    launch = pending_launches.pop(code_key, None)

    if launch is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired Godot launch",
        )

    session = smart.active_sessions.get(
        launch["session_id"]
    )

    if (
        session is None
        or time.time() >= launch["expires"]
        or time.time() >= session["expires_at"]
    ):
        raise HTTPException(
            status_code=401,
            detail="Godot launch has expired",
        )

    credential = secrets.token_urlsafe(32)

    desktop_credentials[
        hash_secret(credential)
    ] = {
        "session_id": launch["session_id"],
        "expires": session["expires_at"],
    }

    return JSONResponse(
        {
            "desktop_session": credential,
            "patient": session["patient"],
            "expires_in": max(
                0,
                int(session["expires_at"] - time.time()),
            ),
        },
        headers={"Cache-Control": "no-store"},
    )



@app.get("/api/desktop/case")
def get_desktop_case(request: Request):
    _, session = resolve_desktop_session(request)

    case = session.get("working_case")

    if case is None:
        raise HTTPException(
            status_code=404,
            detail="No working case is open",
        )

    initial = case.get("_initial_state")

    can_reset = False

    if initial is not None:
        can_reset = (
            case["teeth"] != initial["teeth"]
            or case["measurements"] != initial["measurements"]
        )

    return JSONResponse(
        {
            "patient": session["patient"],
            "encounter": session.get("selected_encounter"),
            "revision": case["revision"],
            "recorded_teeth": case["recorded_teeth"],
            "teeth": case["teeth"],
            "measurements": case["measurements"],
            "can_undo": bool(case.get("_undo")),
            "can_redo": bool(case.get("_redo")),
            "can_reset": can_reset,
            **smart.get_missing_spans(case),
        },
        headers={"Cache-Control": "no-store"},
    )



@app.post("/api/desktop/disconnect")
def desktop_disconnect(request: Request):
    require_local(request)

    token = request.headers.get(DESKTOP_HEADER)

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Desktop credential required",
        )

    key = hash_secret(token)

    if key not in desktop_credentials:
        raise HTTPException(
            status_code=401,
            detail="Unknown desktop credential",
        )

    del desktop_credentials[key]

    return {"disconnected": True}



@app.get("/api/desktop/patient")
def get_desktop_patient(request: Request):
    _, session = resolve_desktop_session(request)

    patient_id = session["patient"]

    url = (
        smart.ISSUER.rstrip("/")
        + "/Patient/"
        + quote(patient_id, safe="")
    )

    try:
        patient = smart.request_json(
            url,
            headers={
                "Authorization": (
                    "Bearer " + session["access_token"]
                ),
                "Accept": "application/fhir+json",
            },
        )
    except HTTPError as error:
        raise HTTPException(
            status_code=502,
            detail=(
                "FHIR Patient retrieval failed: HTTP "
                + str(error.code)
            ),
        ) from error
    except (URLError, ValueError) as error:
        raise HTTPException(
            status_code=502,
            detail=(
                "FHIR Patient retrieval failed: "
                + type(error).__name__
            ),
        ) from error

    if (
        patient.get("resourceType") != "Patient"
        or patient.get("id") != patient_id
    ):
        raise HTTPException(
            status_code=502,
            detail="Unexpected FHIR Patient resource",
        )

    display_name = None

    for name in patient.get("name", []):
        if not isinstance(name, dict):
            continue

        if name.get("text"):
            display_name = str(name["text"])
            break

        parts = [
            str(part)
            for part in name.get("given", [])
            if part
        ]

        if name.get("family"):
            parts.append(str(name["family"]))

        if parts:
            display_name = " ".join(parts)
            break

    return JSONResponse(
        {
            "id": patient_id,
            "name": display_name,
        },
        headers={"Cache-Control": "no-store"},
    )

@app.get("/api/desktop/terminology")
def get_desktop_terminology(request: Request):
    resolve_desktop_session(request)

    return {
        "terminology": load_knowledge(None)["terminology"]
    }

@app.get("/api/desktop/media")
def get_desktop_media(request: Request):
    resolve_desktop_session(request)

    return JSONResponse(
        {"media": load_media()},
        headers={"Cache-Control": "no-store"},
    )