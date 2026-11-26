
import base64
import hashlib
import html
import json
import os
import secrets
import ssl
import time

from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from dotenv import load_dotenv  # type: ignore
from fastapi import FastAPI, HTTPException, Request as WebRequest
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from main import (
    open_case,
    get_missing_spans,
    edit_case,
    undo_case,
    redo_case,
    reset_case,
    evaluate_session,
)




# --------------------------------------------------
# Configuration
# --------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

ISSUER = os.environ["SMART_ISSUER"]
REDIRECT_URI = os.environ["SMART_REDIRECT_URI"]
CLIENT_ID = os.environ["SMART_CLIENT_ID"]
CLIENT_SECRET = os.environ["SMART_CLIENT_SECRET"]

certificate = Path(os.environ["OPENEMR_CA_CERT"])

if not certificate.is_absolute():
    certificate = ROOT / certificate

SSL_CONTEXT = ssl.create_default_context(
    cafile=str(certificate)
)

DISCOVERY_URL = (
    ISSUER.rstrip("/")
    + "/.well-known/smart-configuration"
)

SCOPES = (
    "openid fhirUser online_access "
    "launch launch/patient "
    "api:fhir api:oemr "
    "user/Patient.rs "
    "user/Encounter.rs "
    "user/Condition.rs "
    "user/Observation.rs "
    "user/AllergyIntolerance.rs "
    "user/MedicationRequest.rs "
    "user/Procedure.rs "
    "user/ServiceRequest.rs "
    "user/DocumentReference.rs "
    "user/soap_note.crus "
    "user/document.crs"
)

LAUNCH_LIFETIME = 600
SESSION_LIFETIME = 3600
SESSION_COOKIE = "cdss_session"

FHIR_ADAPTER = "http://localhost:8200"

app = FastAPI(title="Prosthodontic CDSS Backend")

# Local, single-process stores.
pending_launches = {}
active_sessions = {}


# --------------------------------------------------
# HTTPS and encoding
# --------------------------------------------------

def base64url(data):
    return (
        base64.urlsafe_b64encode(data)
        .rstrip(b"=")
        .decode("ascii")
    )


def request_json(url, data=None, headers=None):
    request = Request(
        url,
        data=data,
        headers=headers or {},
        method="POST" if data is not None else "GET",
    )

    with urlopen(
        request,
        timeout=15,
        context=SSL_CONTEXT,
    ) as response:
        result = json.load(response)

    if not isinstance(result, dict):
        raise ValueError("Expected a JSON object")

    return result


# --------------------------------------------------
# SMART configuration discovery
# --------------------------------------------------

def discover_smart():
    try:
        config = request_json(DISCOVERY_URL)

        if config.get("issuer") != ISSUER:
            raise ValueError("Unexpected SMART issuer")

        for name in (
            "authorization_endpoint",
            "token_endpoint",
        ):
            endpoint = config.get(name)

            if (
                not isinstance(endpoint, str)
                or not endpoint.startswith(
                    "https://localhost/"
                )
            ):
                raise ValueError(
                    f"Invalid SMART endpoint: {name}"
                )

        return config

    except (
        HTTPError,
        URLError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "SMART discovery failed: "
                + type(exc).__name__
            ),
        ) from exc


# --------------------------------------------------
# Session lifetime
# --------------------------------------------------

def clear_expired():
    now = time.time()

    for state, transaction in list(
        pending_launches.items()
    ):
        if now - transaction["created"] > LAUNCH_LIFETIME:
            del pending_launches[state]

    for session_id, session in list(
        active_sessions.items()
    ):
        if now >= session["expires_at"]:
            del active_sessions[session_id]


def authorized_session(request: WebRequest):
    clear_expired()

    session_id = request.cookies.get(SESSION_COOKIE)

    if not session_id:
        raise HTTPException(
            status_code=401,
            detail="No active CDSS session",
        )

    session = active_sessions.get(session_id)

    if session is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired CDSS session",
        )

    return session


# --------------------------------------------------
# SMART launch
# --------------------------------------------------

@app.get("/launch")
def launch(iss: str, launch: str):
    if iss != ISSUER:
        raise HTTPException(
            status_code=400,
            detail="Unrecognized SMART issuer",
        )

    config = discover_smart()
    clear_expired()

    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)

    challenge = base64url(
        hashlib.sha256(
            verifier.encode("ascii")
        ).digest()
    )

    pending_launches[state] = {
        "created": time.time(),
        "verifier": verifier,
        "token_endpoint": config["token_endpoint"],
    }

    parameters = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
        "aud": iss,
        "launch": launch,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }

    authorization_url = (
        config["authorization_endpoint"]
        + "?"
        + urlencode(parameters)
    )

    return RedirectResponse(
        authorization_url,
        status_code=302,
    )


# --------------------------------------------------
# Authorization callback
# --------------------------------------------------

@app.get("/callback")
def callback(
    state: str | None = None,
    code: str | None = None,
    error: str | None = None,
):
    if not state:
        raise HTTPException(
            status_code=400,
            detail="Missing OAuth state",
        )

    transaction = pending_launches.pop(state, None)

    if transaction is None:
        raise HTTPException(
            status_code=400,
            detail="Invalid OAuth state",
        )

    if (
        time.time() - transaction["created"]
        > LAUNCH_LIFETIME
    ):
        raise HTTPException(
            status_code=400,
            detail="OAuth launch expired",
        )

    if error:
        raise HTTPException(
            status_code=400,
            detail="OpenEMR authorization failed",
        )

    if not code:
        raise HTTPException(
            status_code=400,
            detail="Missing authorization code",
        )

    # --------------------------------------------------
    # Token exchange
    # --------------------------------------------------

    payload = urlencode({
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": transaction["verifier"],
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }

    try:
        token = request_json(
            transaction["token_endpoint"],
            data=payload,
            headers=headers,
        )

    except HTTPError as exc:
        error_body = exc.read().decode(
            "utf-8",
            errors="replace",
        )

        print(
            f"OAuth token error ({exc.code}): "
            f"{error_body[:1000]}",
            flush=True,
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "OAuth token exchange failed: "
                f"HTTP {exc.code}"
            ),
        ) from exc

    except (
        URLError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "OAuth token exchange failed: "
                + type(exc).__name__
            ),
        ) from exc

    access_token = token.get("access_token")

    if not isinstance(access_token, str) or not access_token:
        raise HTTPException(
            status_code=502,
            detail="Missing OAuth access token",
        )

    token_type = token.get("token_type", "Bearer")

    if (
        not isinstance(token_type, str)
        or token_type.lower() != "bearer"
    ):
        raise HTTPException(
            status_code=502,
            detail="Unsupported OAuth token type",
        )

    # --------------------------------------------------
    # Authorized patient and encounter context
    # --------------------------------------------------

    patient = token.get("patient")
    encounter = token.get("encounter")

    if not isinstance(patient, str) or not patient:
        raise HTTPException(
            status_code=422,
            detail="Missing SMART patient context",
        )

    if encounter is not None and not isinstance(
        encounter, str
    ):
        raise HTTPException(
            status_code=502,
            detail="Invalid SMART encounter context",
        )

    # --------------------------------------------------
    # Create an authenticated CDSS session
    # --------------------------------------------------

    clear_expired()

    session_id = secrets.token_urlsafe(32)

    try:
        token_lifetime = int(
            token.get(
                "expires_in",
                SESSION_LIFETIME,
            )
        )
    except (ValueError, TypeError):
        token_lifetime = SESSION_LIFETIME

    lifetime = max(
        1,
        min(
            token_lifetime,
            SESSION_LIFETIME,
        ),
    )

    active_sessions[session_id] = {
        "patient": patient,
        "encounter": encounter,
        "issuer": ISSUER,
        "scope": token.get("scope", ""),
        "access_token": access_token,
        "expires_at": time.time() + lifetime,
    }

    # Only the opaque session ID is stored in the browser.
    # The OAuth access token remains on the server.

    result = RedirectResponse(
        url="/session",
        status_code=303,
    )

    result.set_cookie(
        key=SESSION_COOKIE,
        value=session_id,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=lifetime,
        path="/",
    )

    return result


# --------------------------------------------------
# Authorized session inspection
# --------------------------------------------------

@app.get(
    "/session",
    response_class=HTMLResponse,
)
def session_page(request: WebRequest):
    session = authorized_session(request)

    visible = {
        "authorization": "successful",
        "patient": session["patient"],
        "encounter": session["encounter"],
        "issuer": session["issuer"],
    }

    output = html.escape(
        json.dumps(
            visible,
            indent=2,
        )
    )

    return HTMLResponse(
        "<h2>Prosthodontic CDSS</h2>"
        "<p>SMART authorization successful.</p>"
        "<pre>" + output + "</pre>"
    )


@app.get("/api/session")
def session_context(request: WebRequest):
    session = authorized_session(request)

    return {
        "patient": session["patient"],
        "encounter": session["encounter"],
        "issuer": session["issuer"],
        "scope": session["scope"],
    }


# --------------------------------------------------
# Authorized FHIR encounter retrieval
# --------------------------------------------------

@app.get("/api/encounters")
def get_patient_encounters(request: WebRequest):
    session = authorized_session(request)

    patient = session["patient"]
    access_token = session["access_token"]

    # Search encounters belonging to the patient
    # supplied by the authenticated SMART launch.

    query = urlencode({
        "patient": patient,
    })

    url = (
        ISSUER.rstrip("/")
        + "/Encounter?"
        + query
    )

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/fhir+json",
    }

    try:
        bundle = request_json(
            url,
            headers=headers,
        )

    except HTTPError as exc:
        if exc.code in (401, 403):
            raise HTTPException(
                status_code=502,
                detail=(
                    "OpenEMR rejected authorized "
                    "FHIR encounter retrieval: "
                    f"HTTP {exc.code}"
                ),
            ) from exc

        raise HTTPException(
            status_code=502,
            detail=(
                "FHIR encounter retrieval failed: "
                f"HTTP {exc.code}"
            ),
        ) from exc

    except (
        URLError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "FHIR encounter retrieval failed: "
                + type(exc).__name__
            ),
        ) from exc

    if (
        bundle.get("resourceType") != "Bundle"
        or bundle.get("type") not in ("searchset", "collection")
        or not isinstance(bundle.get("entry", []), list)
    ):
        raise HTTPException(
            status_code=502,
            detail="Unexpected FHIR encounter search response",
        )

    encounters = []

    for entry in bundle.get("entry", []):
        if not isinstance(entry, dict):
            continue

        resource = entry.get("resource", {})

        if not isinstance(resource, dict):
            continue

        if resource.get("resourceType") != "Encounter":
            continue

        subject = resource.get("subject") or {}

        if not isinstance(subject, dict):
            continue

        subject_reference = subject.get("reference", "")

        # Do not include encounters belonging to another
        # patient if an unexpected resource is returned.

        if subject_reference not in (
            f"Patient/{patient}",
            ISSUER.rstrip("/") + f"/Patient/{patient}",
        ):
            continue

        encounters.append({
            "id": resource.get("id"),
            "status": resource.get("status"),
            "class": resource.get("class"),
            "type": resource.get("type", []),
            "period": resource.get("period"),
        })

    # This initial endpoint returns the first search page.
    # Pagination can be added if the server returns next links.

    has_next_page = any(
        isinstance(link, dict)
        and link.get("relation") == "next"
        for link in bundle.get("link", [])
    )

    return {
        "patient": patient,
        "encounters": encounters,
        "has_next_page": has_next_page,
    }


# --------------------------------------------------
# Open a working clinical case for the selected encounter
# --------------------------------------------------

class EncounterSelection(BaseModel):
    encounter_id: str

# Select a missing span of teeth for the working case
class SpanSelection(BaseModel):
    spans: list[list[str]]

@app.post("/api/case/open")
def open_selected_case(selection: EncounterSelection, request: WebRequest):
    session = authorized_session(request)

    # Patient context comes exclusively from the SMART session.
    patient_uuid = session["patient"]
    encounter_uuid = selection.encounter_id

    resolve_url = (
        f"{FHIR_ADAPTER}/internal/resolve-identifiers/"
        f"{patient_uuid}/{encounter_uuid}"
    )

    try:
        identifiers = request_json(resolve_url)

        working_case = open_case(
            identifiers["patient_id"],
            identifiers["encounter_id"],
        )

    except HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Clinical adapter returned HTTP {exc.code}",
        ) from exc

    except (URLError, ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Clinical case initialization failed: "
                + type(exc).__name__
            ),
        ) from exc

    # A newly selected encounter replaces the previous working case.
    session["selected_encounter"] = encounter_uuid
    session["working_case"] = working_case
    session["selected_spans"] = []

    return {
        "patient": patient_uuid,
        "encounter": encounter_uuid,
        "revision": working_case["revision"],
        "recorded_teeth": working_case["recorded_teeth"],
        "teeth": working_case["teeth"],
        "measurements": working_case["measurements"],
    }
# Exposes the missing spans of the working case for the selected encounter
@app.get("/api/case/spans")
def get_case_spans(request: WebRequest):
    session = authorized_session(request)

    if "working_case" not in session:
        raise HTTPException(
            status_code=400,
            detail="Open a clinical case first",
        )

    return get_missing_spans(session["working_case"])


# Selects a missing span of teeth for the working case
@app.post("/api/case/select-spans")
def select_case_spans(selection: SpanSelection, request: WebRequest):
    session = authorized_session(request)

    if "working_case" not in session:
        raise HTTPException(
            status_code=400,
            detail="Open a clinical case first",
        )

    available = get_missing_spans(
        session["working_case"]
    )["selectable_spans"]

    selected = [
        span for span in selection.spans
        if span in available
    ]

    single_tooth_spans = [
        span for span in selected
        if len(span) == 1
    ]

    unsupported_spans = [
        span for span in selected
        if len(span) > 1
    ]

    session["selected_spans"] = single_tooth_spans

    return {
        "selected_spans": single_tooth_spans,
        "unsupported_spans": unsupported_spans,
        "message": (
            "The current demonstration supports single-tooth spans only."
            if unsupported_spans else None
        ),
    }

# --------------------------------------------------
# Service health
# --------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


# --------------------------------------------------
# Working-case editing and clinical evaluation
# --------------------------------------------------

class CaseEdit(BaseModel):
    tooth: str | None = None
    state: str | None = None
    hba1c: float | None = None




def current_working_case(request: WebRequest):
    session = authorized_session(request)

    if "working_case" not in session:
        raise HTTPException(
            status_code=400,
            detail="Open a clinical case first",
        )

    return session["working_case"]


def working_case_response(case):
    return {
        "revision": case["revision"],
        "teeth": case["teeth"],
        "measurements": case["measurements"],
        **get_missing_spans(case),
    }


@app.patch("/api/case")
def update_working_case(edit: CaseEdit, request: WebRequest):
    case = current_working_case(request)

    edit_case(
        case,
        tooth=edit.tooth,
        state=edit.state,
        hba1c=edit.hba1c,
    )

    return working_case_response(case)


@app.post("/api/case/undo")
def undo_working_case(request: WebRequest):
    case = current_working_case(request)
    changed = undo_case(case)

    return {
        "changed": changed,
        **working_case_response(case),
    }


@app.post("/api/case/redo")
def redo_working_case(request: WebRequest):
    case = current_working_case(request)
    changed = redo_case(case)

    return {
        "changed": changed,
        **working_case_response(case),
    }


@app.post("/api/case/reset")
def reset_working_case(request: WebRequest):
    case = current_working_case(request)
    changed = reset_case(case)

    return {
        "changed": changed,
        **working_case_response(case),
    }


# Clinical evaluation of the working case for the selected tooth
@app.post("/api/case/evaluate")
def evaluate_working_case(request: WebRequest):
    session = authorized_session(request)

    if "working_case" not in session:
        raise HTTPException(
            status_code=400,
            detail="Open a clinical case first",
        )
    case = session["working_case"]
    selected_spans = session.get("selected_spans", [])

    if not selected_spans:
        raise HTTPException(
            status_code=400,
            detail="Select a missing-tooth span before evaluation",
        )
    available_spans = get_missing_spans(case)["selectable_spans"]

    if any(span not in available_spans for span in selected_spans):
     raise HTTPException(
        status_code=400,
        detail=(
            "The selected span is no longer valid. "
            "Review the odontogram and select a span again."
        ),
     )
    
    

    results = []

    for span in selected_spans:
        if len(span) > 1:
            continue

        tooth = span[0]

        results.append({
            "span": span,
            "evaluation": evaluate_session(case, tooth),
        })

    return {
        "revision": case["revision"],
        "results": results,
    }

