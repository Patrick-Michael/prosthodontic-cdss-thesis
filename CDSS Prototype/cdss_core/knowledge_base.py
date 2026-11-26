
from builtins import FileNotFoundError
import sqlite3
from contextlib import closing
from copy import deepcopy
from functools import lru_cache
from pathlib import Path


DATABASE = Path(__file__).resolve().parent / "knowledge.db"


@lru_cache(maxsize=4)
def _load_cached_knowledge(guideline_id):
    """
    Load and cache the descriptive knowledge associated
    with a ruleset.
    """

    if not DATABASE.is_file():
        raise FileNotFoundError(
            f"Knowledge database not found: {DATABASE}"
        )

    uri = DATABASE.resolve().as_uri() + "?mode=ro"

    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.row_factory = sqlite3.Row

        def rows(query, parameters=()):
            return [
                dict(row)
                for row in connection.execute(query, parameters)
            ]

        treatments = rows(
            """
            SELECT
                treatment_id,
                guideline_id,
                treatment_code,
                name,
                summary,
                explanation,
                clinical_detail
            FROM treatments
            WHERE guideline_id = ?
               OR (
                   guideline_id IS NULL
                   AND treatment_code IS NULL
               )
            ORDER BY rowid
            """,
            (guideline_id,)
        )

        for treatment in treatments:
            treatment_id = treatment["treatment_id"]

            treatment["attributes"] = rows(
                """
                SELECT
                    ta.attribute_id,
                    ad.label,
                    ad.explanation AS attribute_explanation,
                    ad.display_order,
                    ta.value_type,
                    ta.value,
                    ta.display_value,
                    ta.explanation,
                    ta.clinical_detail
                FROM treatment_attributes AS ta
                JOIN attribute_definitions AS ad
                    ON ad.attribute_id = ta.attribute_id
                WHERE ta.treatment_id = ?
                ORDER BY ad.display_order
                """,
                (treatment_id,)
            )

            procedures = rows(
                """
                SELECT
                    p.procedure_id,
                    p.procedure_type,
                    p.title,
                    p.summary,
                    p.explanation,
                    p.clinical_detail
                FROM treatment_procedures AS tp
                JOIN procedures AS p
                    ON p.procedure_id = tp.procedure_id
                WHERE tp.treatment_id = ?
                ORDER BY tp.display_order
                """,
                (treatment_id,)
            )

            for procedure in procedures:
                procedure["steps"] = rows(
                    """
                    SELECT
                        step_id,
                        step_order,
                        title,
                        explanation,
                        clinical_detail,
                        scene_key,
                        duration_note
                    FROM procedure_steps
                    WHERE procedure_id = ?
                    ORDER BY step_order
                    """,
                    (procedure["procedure_id"],)
                )

            treatment["procedures"] = procedures

        rule_details = rows(
            """
            SELECT
                rule_id,
                clinical_detail,
                limitations
            FROM rules
            WHERE guideline_id = ?
            """,
            (guideline_id,)
        )

        terminology = rows(
            """
            SELECT
                term_id,
                code_system,
                code,
                display_label,
                explanation,
                clinical_detail
            FROM terminology
            ORDER BY term_id
            """
        )

    return {
        "treatments": treatments,
        "rule_details": {
            rule["rule_id"]: {
                "clinical_detail": rule["clinical_detail"],
                "limitations": rule["limitations"]
            }
            for rule in rule_details
        },
        "terminology": terminology
    }


def load_knowledge(guideline_id):
    """
    Return the cached knowledge without exposing
    the shared cache to modification.
    """

    return deepcopy(_load_cached_knowledge(guideline_id))

def load_media():
    """
    Return the independent media catalogue from
    the local knowledge database.
    """
    if not DATABASE.is_file():
        raise FileNotFoundError(
            f"Knowledge database not found: {DATABASE}"
        )

    uri = DATABASE.resolve().as_uri() + "?mode=ro"

    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.row_factory = sqlite3.Row

        return [
            dict(row)
            for row in connection.execute(
                """
                SELECT
                    media_id,
                    title,
                    media_type,
                    file_path,
                    creator,
                    source_url,
                    license_name,
                    license_url,
                    modifications,
                    attribution_required,
                    notes
                FROM media_assets
                ORDER BY media_type, title, media_id
                """
            )
        ]
