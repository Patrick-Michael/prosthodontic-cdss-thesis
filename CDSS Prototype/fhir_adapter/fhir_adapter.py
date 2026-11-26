
import os
import math
import uuid

import pymysql
from fastapi import FastAPI, HTTPException

app = FastAPI(title="CDSS FHIR Adapter")

SNOMED = "http://snomed.info/sct"
LOINC = "http://loinc.org"
DENTAL_BASE = "http://hl7.org/fhir/us/dental-data-exchange"

DENTAL_CATEGORY = {
    "coding": [{
        "system": f"{DENTAL_BASE}/CodeSystem/dental-category",
        "code": "dental",
        "display": "Dental"
    }]
}


def db_connect():
    return pymysql.connect(
        host=os.getenv("DB_HOST", "mysql"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "cdss_adapter"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "openemr"),
        ssl_disabled=os.getenv("DB_SSL_DISABLED", "true").lower() == "true",
        connect_timeout=5,
        read_timeout=10,
        cursorclass=pymysql.cursors.DictCursor,
    )


def fhir_code(stored_code):
    if not stored_code or ":" not in stored_code:
        raise ValueError("Missing or invalid terminology code")

    system, code = stored_code.split(":", 1)

    systems = {
        "SNOMED-CT": SNOMED,
        "LOINC": LOINC
    }

    if system not in systems or not code.strip():
        raise ValueError(f"Unsupported terminology code: {stored_code}")

    return {
        "coding": [{
            "system": systems[system],
            "code": code.strip()
        }]
    }


def to_fhir(row):
    subject = {"reference": f"Patient/{row['pid']}"}
    encounter = {"reference": f"Encounter/{row['encounter']}"}

    if row["formdir"] == "LBF_DENTAL_ODONTOGRAM":
        anatomy = fhir_code(row["field_codes"])
        status = fhir_code(row["selected_codes"])

        if row["field_value"] == "tooth_present":
            if not row["form_date"]:
                raise ValueError("Missing tooth assessment timestamp")

            return {
                "resourceType": "Observation",
                "meta": {"profile": [
                    f"{DENTAL_BASE}/StructureDefinition/dental-findings"
                ]},
                "status": "unknown",
                "category": [DENTAL_CATEGORY],
                "code": {
                    "coding": [{
                        "system": LOINC,
                        "code": "32885-6"
                    }]
                },
                "subject": subject,
                "encounter": encounter,
                "effectiveDateTime": row["form_date"].date().isoformat(),
                "valueCodeableConcept": status,
                "bodySite": anatomy
            }

        if row["field_value"] == "tooth_absent":
            return {
                "resourceType": "Condition",
                "meta": {"profile": [
                    f"{DENTAL_BASE}/StructureDefinition/dental-condition"
                ]},
                "category": [DENTAL_CATEGORY],
                "code": status,
                "bodySite": [anatomy],
                "subject": subject,
                "encounter": encounter
            }

        raise ValueError(
            f"Unsupported tooth status: {row['field_value']}"
        )

    if row["formdir"] == "LBF_HBA1C" and row["field_id"] == "hba1c_value":
        try:
            value = float(row["field_value"])
        except (ValueError, TypeError):
            raise ValueError("Invalid HbA1c value")

        if not math.isfinite(value):
            raise ValueError("Invalid HbA1c value")

        return {
            "resourceType": "Observation",
            "meta": {"profile": [
                "http://hl7.org/fhir/us/core/StructureDefinition/us-core-observation-lab"
            ]},
            "status": "unknown",
            "category": [{
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                    "code": "laboratory"
                }]
            }],
            "code": fhir_code(row["field_codes"]),
            "subject": subject,
            "encounter": encounter,
            "valueQuantity": {
                "value": value,
                "unit": "%",
                "system": "http://unitsofmeasure.org",
                "code": "%"
            }
        }

    raise ValueError("Unsupported clinical field")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/db-test")
def database_test():
    try:
        with db_connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS count FROM lbf_data")
                count = cursor.fetchone()["count"] # type: ignore

        return {
            "database": "connected",
            "lbf_records": count
        }

    except pymysql.MySQLError:
        raise HTTPException(503, "Database connection failed")


# Resolve SMART FHIR UUIDs to OpenEMR internal identifiers.
# The SMART launcher must authorize patient and encounter
# selection before calling this internal adapter operation.

@app.get("/internal/resolve-identifiers/{patient_uuid}/{encounter_uuid}")
def resolve_identifiers(patient_uuid: str, encounter_uuid: str):
    try:
        patient_bytes = uuid.UUID(patient_uuid).bytes
        encounter_bytes = uuid.UUID(encounter_uuid).bytes
    except ValueError:
        raise HTTPException(400, "Invalid FHIR UUID")

    query = """
        SELECT
            p.pid AS patient_id,
            e.encounter AS encounter_id
        FROM patient_data AS p
        JOIN form_encounter AS e
            ON e.pid = p.pid
        WHERE p.uuid = %s
            AND e.uuid = %s
    """

    try:
        with db_connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, (patient_bytes, encounter_bytes))
                result = cursor.fetchone()

    except pymysql.MySQLError:
        raise HTTPException(503, "Identifier lookup failed")

    if result is None:
        raise HTTPException(404, "Patient encounter not found")

    return {
        "patient_id": result["patient_id"],
        "encounter_id": result["encounter_id"]
    }


@app.get("/fhir/patients/{pid}/encounters/{encounter}")
def get_fhir(pid: int, encounter: int):
    query = """
        SELECT
            f.form_id AS instance_id,
            f.formdir,
            f.pid,
            f.encounter,
            f.date AS form_date,
            d.field_id,
            d.field_value,
            lo.codes AS field_codes,
            li.codes AS selected_codes
        FROM forms AS f
        JOIN lbf_data AS d
            ON d.form_id = f.form_id
        JOIN layout_options AS lo
            ON lo.form_id = f.formdir
            AND lo.field_id = d.field_id
        LEFT JOIN list_options AS li
            ON li.list_id = lo.list_id
            AND li.option_id = d.field_value
        WHERE f.deleted = 0
            AND f.pid = %s
            AND f.encounter = %s
            AND (
                (
                    f.formdir = 'LBF_DENTAL_ODONTOGRAM'
                    AND d.field_id LIKE 'tooth_%%'
                )
                OR (
                    f.formdir = 'LBF_HBA1C'
                    AND d.field_id = 'hba1c_value'
                )
            )
            AND d.field_value IS NOT NULL
            AND d.field_value <> ''
        ORDER BY f.id, lo.seq
    """

    try:
        with db_connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, (pid, encounter))
                rows = cursor.fetchall()

    except pymysql.MySQLError:
        raise HTTPException(503, "Database query failed")

    if not rows:
        raise HTTPException(404, "No recorded clinical data found")

    try:
        resources = [to_fhir(row) for row in rows]
    except ValueError as error:
        raise HTTPException(422, str(error))

    entries = []

    for row, resource in zip(rows, resources):
        source_id = f"{row['instance_id']}:{row['field_id']}"

        resource_id = str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"openemr:lbf:{resource['resourceType']}:{source_id}"
        ))

        resource["id"] = resource_id

        entries.append({
            "fullUrl": f"urn:uuid:{resource_id}",
            "resource": resource
        })

    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": entries
    }
