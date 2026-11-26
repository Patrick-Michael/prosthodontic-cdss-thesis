
import json
import re
import subprocess
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

JAVA_CLASSPATH = (
    f"{PROJECT_ROOT / 'bridge'};"
    f"{PROJECT_ROOT / 'gdl_runtime' / 'BOOT-INF' / 'lib' / '*'}"
)

OUTPUT_ROLES = {
    "Treatment option": "treatment",
    "Decision status": "status"
}

STATUSES = {"Available", "Caution", "Excluded"}

ASSIGNMENT_PATTERN = re.compile(
    r"^\$(\w+)\|[^|]*\|=([^|]+)\|([^|]*)\|$"
)


def load_guideline(guideline_path):
    """
    Load the selected GDL2 guideline.
    """

    path = Path(guideline_path).resolve()

    with path.open("r", encoding="utf-8") as file:
        guideline = json.load(file)

    return path, guideline


def get_bindings(guideline, binding_type):
    """
    Collect the elements declared as INPUT or OUTPUT
    in the guideline.
    """

    bindings = guideline["definition"]["data_bindings"]

    elements = {}

    for binding in bindings.values():
        if binding["type"] != binding_type:
            continue

        for element_id, element in binding["elements"].items():
            if element_id in elements:
                raise ValueError(
                    f"Duplicate {binding_type} element: {element_id}"
                )

            elements[element_id] = element

    return elements


def build_request(guideline_path, guideline, inputs):
    """
    Prepare a Java bridge request using the selected
    guideline and supplied GDL2 input values.
    """

    allowed_inputs = get_bindings(guideline, "INPUT")

    for item in inputs:
        element_id = item["element_id"]

        if element_id not in allowed_inputs:
            raise ValueError(
                f"Input {element_id} is not declared by the guideline"
            )

        if "type" not in item:
            raise ValueError(
                f"Input {element_id} has no datatype"
            )

    return {
        "guideline": str(guideline_path),
        "inputs": inputs
    }


def run_bridge(request):
    """
    Execute the existing Java bridge and return its
    parsed JSON response.
    """

    with tempfile.TemporaryDirectory() as directory:
        request_path = Path(directory) / "request.json"

        request_path.write_text(
            json.dumps(request),
            encoding="utf-8"
        )

        command = [
            "java",
            "-cp",
            JAVA_CLASSPATH,
            "GdlBridge",
            str(request_path)
        ]

        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60
        )

        if completed.returncode != 0:
            raise RuntimeError(
                f"GDL2 execution failed:\n{completed.stderr}"
            )

    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "Java bridge did not return valid JSON"
        ) from error


def get_output_roles(guideline):
    """
    Identify the treatment and status elements from
    the guideline's declared output terminology.
    """

    output_elements = get_bindings(guideline, "OUTPUT")

    language = guideline["language"]["original_language"]
    language_code = language.split("::")[-1]

    terms = guideline["ontology"]["term_definitions"][
        language_code
    ]["terms"]

    roles = {}

    for element_id in output_elements:
        label = terms[element_id]["text"]

        if label in OUTPUT_ROLES:
            role = OUTPUT_ROLES[label]

            if role in roles:
                raise ValueError(
                    f"Multiple output elements define {role}"
                )

            roles[role] = element_id

    if set(roles) != {"treatment", "status"}:
        raise ValueError(
            "Guideline must define Treatment option "
            "and Decision status outputs"
        )

    return roles


def parse_assignment(statement):
    """
    Extract an assigned GDL2 coded-text value.
    """

    match = ASSIGNMENT_PATTERN.fullmatch(statement)

    if not match:
        raise ValueError(
            f"Unsupported GDL2 action: {statement}"
        )

    element_id, coded_value, display = match.groups()

    if "::" not in coded_value:
        raise ValueError(
            f"Unsupported coded-text assignment: {statement}"
        )

    terminology, code = coded_value.split("::", 1)

    return {
        "element_id": element_id,
        "terminology": terminology,
        "code": code,
        "display": display
    }


def process_results(response, guideline):
    """
    Extract all fired-rule findings and group them
    by the assigned treatment terminology identifier.
    """

    guideline_id = response["guideline_id"]

    if guideline_id != guideline["id"]:
        raise ValueError("Bridge returned a different guideline")

    fired_rules = response["fired_rules"][guideline_id]

    executed_rules = response["debug"][guideline_id][
        "rulesInOrderOfExecution"
    ]

    roles = get_output_roles(guideline)

    groups = {}
    processed_rules = set()

    for rule in executed_rules:
        rule_id = rule["ruleId"]

        if rule_id not in fired_rules:
            continue

        if rule_id in processed_rules:
            raise ValueError(f"Duplicate executed rule: {rule_id}")

        assignments = {}

        for statement in rule["thenStatements"]:
            assignment = parse_assignment(statement)
            element_id = assignment["element_id"]

            if element_id in assignments:
                raise ValueError(
                    f"Rule {rule_id} assigns {element_id} more than once"
                )

            assignments[element_id] = assignment

        treatment = assignments.get(roles["treatment"])
        status = assignments.get(roles["status"])

        if treatment is None or status is None:
            raise ValueError(
                f"Rule {rule_id} has incomplete decision outputs"
            )

        if status["display"] not in STATUSES:
            raise ValueError(
                f"Unsupported decision status: {status['display']}"
            )

        treatment_key = (
            treatment["terminology"],
            treatment["code"]
        )

        if treatment_key not in groups:
            groups[treatment_key] = {
                "treatment": {
                    "terminology": treatment["terminology"],
                    "code": treatment["code"],
                    "name": treatment["display"]
                },
                "findings": []
            }

        groups[treatment_key]["findings"].append({
            "rule_id": rule_id,
            "status": status["display"],
            "status_code": status["code"],
            "conditions": rule["whenStatements"]
        })

        processed_rules.add(rule_id)

    if processed_rules != set(fired_rules):
        raise ValueError(
            "Bridge response is missing executed-rule details"
        )

    results = []

    for group in groups.values():
        findings = group["findings"]

        statuses = {
            finding["status"]
            for finding in findings
        }

        if "Excluded" in statuses:
            final_status = "Excluded"

        elif "Available" in statuses:
            final_status = "Available"

        else:
            final_status = "Caution"

        alerts = []

        if final_status != "Excluded":
            alerts = [
                finding["rule_id"]
                for finding in findings
                if finding["status"] == "Caution"
            ]

        group["status"] = final_status
        group["soft_alerts"] = alerts

        results.append(group)

    return results


def get_terms(guideline):
    """
    Return the terminology entries for the guideline's
    original language.
    """
    language = guideline["language"]["original_language"]
    language_code = language.split("::")[-1]

    return guideline["ontology"]["term_definitions"][
        language_code
    ]["terms"]


def process_explanations(response, guideline, inputs):
    """
    Combine guideline terminology with the evaluations
    reported by the GDL2 runtime.

    Clinical conditions are evaluated only by GDL2.
    """
    guideline_id = response["guideline_id"]
    debug = response["debug"][guideline_id]
    terms = get_terms(guideline)
    roles = get_output_roles(guideline)

    # Input explanations
    input_explanations = []

    for item in inputs:
        element_id = item["element_id"]
        term = terms[element_id]

        input_explanations.append({
            "element_id": element_id,
            "label": term["text"],
            "description": term.get("description"),
            "type": item["type"],
            "value": item["value"],
            "unit": item.get("unit")
        })

    # Why and Why-not explanations
    def explain_rule(rule, executed):
        rule_id = rule["ruleId"]
        term = terms[rule_id]

        assignments = {
            assignment["element_id"]: assignment
            for assignment in (
                parse_assignment(statement)
                for statement in rule["thenStatements"]
            )
        }

        treatment = assignments[roles["treatment"]]
        status = assignments[roles["status"]]

        conditions = rule["whenStatements"]

        return {
            "rule_id": rule_id,
            "label": term["text"],
            "description": term.get("description"),
            "treatment": {
                "terminology": treatment["terminology"],
                "code": treatment["code"],
                "name": treatment["display"]
            },
            "status": status["display"],
            "executed": executed,
            "conditions": conditions,
            "failed_conditions": [
                condition
                for condition in conditions
                if False in condition.values()
            ]
        }

    why = [
        explain_rule(rule, True)
        for rule in debug["rulesInOrderOfExecution"]
    ]

    why_not = [
        explain_rule(rule, False)
        for rule in debug["nonExecutedRules"]
    ]

    
    # Associate each input with the rules that use it.
    # Relationships come from GDL2, not from hardcoded mappings.

    rule_explanations = {
        rule["rule_id"]: rule
        for rule in why + why_not
    }

    input_relationships = {
        item["element_id"]: []
        for item in input_explanations
    }

    for rule_id, rule_definition in guideline["definition"]["rules"].items():
        referenced_inputs = set()

        for condition in rule_definition["when"]:
            referenced_inputs.update(
                re.findall(r"\$(gt\d+)\|", condition)
            )

        for element_id in referenced_inputs:
            if element_id not in input_relationships:
                continue

            rule = rule_explanations[rule_id]

            input_relationships[element_id].append({
                "rule_id": rule_id,
                "label": rule["label"],
                "treatment": rule["treatment"],
                "status": rule["status"],
                "executed": rule["executed"]
            })

    for item in input_explanations:
        item["related_rules"] = input_relationships[
            item["element_id"]
        ]

    return {
        "inputs": input_explanations,
        "why": why,
        "why_not": why_not
    }



def evaluate(guideline_path, inputs):
    """
    Execute the GDL2 guideline and return treatment
    results, runtime diagnostics and explanations.
    """

    path, guideline = load_guideline(guideline_path)

    request = build_request(path, guideline, inputs)

    response = run_bridge(request)

    treatments = process_results(response, guideline)

    explanations = process_explanations(
        response,
        guideline,
        request["inputs"]
    )

    return {
        "guideline_id": response["guideline_id"],
        "treatments": treatments,
        "inputs": request["inputs"],
        "runtime_trace": response,
        "explanations": explanations
    }


