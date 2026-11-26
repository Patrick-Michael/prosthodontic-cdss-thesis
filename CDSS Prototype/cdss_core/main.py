
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen
from copy import deepcopy
from inference import evaluate
from knowledge_base import load_knowledge

# 1. Configuration

ROOT = Path(__file__).resolve().parent.parent

FHIR_ADAPTER = "http://localhost:8200"

GUIDELINE = (
    ROOT / "ruleset"
    / "prosthetic_cdss_demo_guidelines.v0.gdl2.json"
)

SNOMED = "http://snomed.info/sct"
LOINC = "http://loinc.org"


# 2. SNOMED CT to FDI permanent tooth mapping

TOOTH_CODES = {
    "245566003": "18", "245567007": "17",
    "245568002": "16", "245570006": "15",
    "245571005": "14", "245572003": "13",
    "245574002": "12", "245575001": "11",

    "245587008": "21", "245586004": "22",
    "245584001": "23", "245583007": "24",
    "245582002": "25", "245579007": "26",
    "245578004": "27", "245577009": "28",

    "245611006": "31", "245610007": "32",
    "245608005": "33", "245607000": "34",
    "245606009": "35", "245604007": "36",
    "245603001": "37", "245602006": "38",

    "245600003": "41", "245599001": "42",
    "245597004": "43", "245596008": "44",
    "245595007": "45", "245592005": "46",
    "245591003": "47", "245590002": "48"
}


def has_code(concept, system, code):
    """Match a clinical code and its terminology system."""
    return any(
        coding.get("system") == system
        and coding.get("code") == code
        for coding in concept.get("coding", [])
    )


def get_tooth(resource):
    """Read a tooth's FDI identifier from its FHIR bodySite."""

    sites = resource.get("bodySite", [])

    if isinstance(sites, dict):
        sites = [sites]

    for site in sites:
        for coding in site.get("coding", []):
            if coding.get("system") == SNOMED:
                tooth = TOOTH_CODES.get(coding.get("code"))

                if tooth:
                    return tooth

    return None


# 3. Retrieve the clinical case

def fetch_bundle(patient_id, encounter_id):
    """Retrieve the selected case from the existing FHIR adapter."""

    patient = quote(str(patient_id), safe="")
    encounter = quote(str(encounter_id), safe="")

    url = (
        f"{FHIR_ADAPTER}/fhir/patients/"
        f"{patient}/encounters/{encounter}"
    )

    with urlopen(url, timeout=15) as response:
        return json.load(response)


# 4. FHIR to working clinical case

def create_session(bundle, patient_id, encounter_id):
    """
    Create a session from the imported FHIR Bundle.

    Temporary prototype assumption:
    all permanent teeth initially present.
    Recorded dental findings override these defaults.
    """

    if bundle.get("resourceType") != "Bundle":
        raise ValueError("Expected a FHIR Bundle")

    teeth = {
        f"{quadrant}{position}": "present"
        for quadrant in range(1, 5)
        for position in range(1, 9)
    }

    recorded_teeth = {}
    hba1c = None

    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        kind = resource.get("resourceType")
        code = resource.get("code", {})

        if kind == "Condition":
            if has_code(code, SNOMED, "234948008"):
                tooth = get_tooth(resource)

                if tooth:
                    recorded_teeth[tooth] = "absent"

        elif kind == "Observation":

            if has_code(code, LOINC, "32885-6"):
                tooth = get_tooth(resource)

                if tooth and has_code(
                    resource.get("valueCodeableConcept", {}),
                    SNOMED,
                    "278661005"
                ):
                    recorded_teeth[tooth] = "present"

            elif has_code(code, LOINC, "4548-4"):
                quantity = resource.get("valueQuantity", {})

                if quantity.get("value") is not None:
                    hba1c = quantity["value"]

    teeth.update(recorded_teeth)

    return {
        "patient_id": str(patient_id),
        "encounter_id": str(encounter_id),
        "revision": 0,
        "source_bundle": bundle,
        "teeth": teeth,
        "recorded_teeth": recorded_teeth,
        "measurements": {
            "hba1c": hba1c
        }
    }

# Determine the missing spans of teeth and the selectable spans based on the session data.
def get_missing_spans(session):
    """Group consecutive missing teeth and identify selectable spans."""

    teeth = session["teeth"]
    missing_spans = []

    for quadrant in range(1, 5):
        current_span = []

        for position in range(1, 9):
            tooth = f"{quadrant}{position}"

            if teeth[tooth] == "absent":
                current_span.append(tooth)
            elif current_span:
                missing_spans.append(current_span)
                current_span = []

        if current_span:
            missing_spans.append(current_span)

    selectable_spans = [
        [tooth for tooth in span if tooth[1] != "8"]
        for span in missing_spans
    ]

    selectable_spans = [
        span for span in selectable_spans if span
    ]

    return {
        "missing_spans": missing_spans,
        "selectable_spans": selectable_spans,
    }



# Workflow Optimization (Undo/Redo) and Case Editing

def _clinical_snapshot(session):
    return {
        "teeth": deepcopy(session["teeth"]),
        "measurements": deepcopy(session["measurements"]),
    }


def _restore_snapshot(session, snapshot):
    session["teeth"] = deepcopy(snapshot["teeth"])
    session["measurements"] = deepcopy(snapshot["measurements"])
    session["revision"] += 1


def edit_case(session, tooth=None, state=None, hba1c=None):
    """Edit the working clinical inputs as one undoable action."""

    previous = _clinical_snapshot(session)
    updated = deepcopy(previous)

    if tooth is not None:
        updated["teeth"][tooth] = state

    if hba1c is not None:
        updated["measurements"]["hba1c"] = hba1c

    if updated == previous:
        return False

    session.setdefault("_initial_state", deepcopy(previous))
    session.setdefault("_undo", []).append(previous)
    session["_redo"] = []

    _restore_snapshot(session, updated)
    return True


def undo_case(session):
    history = session.get("_undo", [])

    if not history:
        return False

    session.setdefault("_redo", []).append(
        _clinical_snapshot(session)
    )

    _restore_snapshot(session, history.pop())
    return True


def redo_case(session):
    history = session.get("_redo", [])

    if not history:
        return False

    session.setdefault("_undo", []).append(
        _clinical_snapshot(session)
    )

    _restore_snapshot(session, history.pop())
    return True


def reset_case(session):
    initial = session.get("_initial_state")

    if initial is None:
        return False

    _restore_snapshot(session, initial)

    session["_undo"] = []
    session["_redo"] = []

    return True


# 5. Current prosthodontic guideline input mapping

def build_prosthodontic_inputs(session, target_tooth):
    """
    Build the six possible inputs for the existing
    posterior single-tooth GDL2 guideline.
    """

    target = str(target_tooth)

    if (
        len(target) != 2
        or target[0] not in "1234"
        or target[1] not in "12345678"
    ):
        raise ValueError("Select a valid permanent tooth")

    teeth = session["teeth"]

    quadrant = int(target[0])
    position = int(target[1])

    mesial = f"{quadrant}{position - 1}"

    distal = (
        f"{quadrant}{position + 1}"
        if position < 8 else None
    )

    mesial_present = teeth[mesial] == "present"

    distal_present = (
        teeth[distal] == "present"
        if distal else False
    )

    distal_count = sum(
        teeth[f"{quadrant}{number}"] == "present"
        for number in range(position + 1, 9)
    )

    inputs = [
        {
            "element_id": "gt0006",
            "type": "boolean",
            "value": teeth[target] == "absent"
        },
        {
            "element_id": "gt0007",
            "type": "boolean",
            "value": target[1] in "45678"
        },
        {
            "element_id": "gt0008",
            "type": "boolean",
            "value": mesial_present
        },
        {
            "element_id": "gt0009",
            "type": "boolean",
            "value": distal_present
        },
        {
            "element_id": "gt0010",
            "type": "count",
            "value": distal_count
        }
    ]

    hba1c = session["measurements"].get("hba1c")

    if hba1c is not None:
        inputs.append({
            "element_id": "gt0038",
            "type": "quantity",
            "value": float(hba1c),
            "unit": "%",
            "precision": 2
        })

    return inputs


# 6. Core entry points

def open_case(patient_id, encounter_id):
    """Initialize the selected patient encounter."""

    bundle = fetch_bundle(patient_id, encounter_id)

    return create_session(
        bundle,
        patient_id,
        encounter_id
    )



def evaluate_session(session, target_tooth):
    """Evaluate the working case and attach cached knowledge."""

    inputs = build_prosthodontic_inputs(
        session,
        target_tooth
    )

    result = evaluate(GUIDELINE, inputs)

    knowledge = load_knowledge(
        result["guideline_id"]
    )

    return {
        "revision": session["revision"],
        "target_tooth": str(target_tooth),
        **result,
        "knowledge": knowledge
    }

