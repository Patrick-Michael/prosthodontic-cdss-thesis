
extends Node

signal case_loaded(data: Dictionary)
signal evaluation_completed(data: Dictionary)
signal connection_error(message: String)
signal media_loaded(catalogue: Dictionary)

const API_URL := "http://127.0.0.1:8201"
const SESSION_HEADER := "X-CDSS-Desktop-Session"

var credential: String = ""
var patient_id: String = ""
var patient_display_name: String = ""
var current_case: Dictionary = {}
var encounters: Array = []

var busy: bool = false
var case_ready: bool = false

var http: HTTPRequest
var encounter_menu: PopupMenu

var main: Control
var assessment: VBoxContainer

var encounter_button: Button
var patient_label: Label
var encounter_label: Label
var encounter_note: Label

var hba1c_input: SpinBox
var measurement_note: Label

var evaluate_button: Button
var actions_note: Label
var terminology: Dictionary = {}
var media_catalogue: Dictionary = {}
# --------------------------------------------------
# Initialization
# --------------------------------------------------
func _sync_span_highlights() -> void:
	main.tooth_controller.set_highlighted_spans(
		assessment.get_selected_spans()
	)
	
func _ready() -> void:
	main = get_parent()

	# MainController must finish initializing its
	# @onready references before this child calls
	# any methods on it.
	await main.ready

	assessment = main.get_node(
		"AppLayout/MainLayout/InformationPanel/"
		+ "InformationMargin/InformationContent/"
		+ "PageContainer/ClinicalAssessmentPage"
	)

	var content: Node = assessment.get_node(
		"AssessmentScroll/AssessmentContent"
	)

	var case_content: Node = content.get_node(
		"CaseHeader/Content/CaseContent"
	)

	encounter_button = case_content.get_node(
		"SelectEncounter"
	)

	patient_label = case_content.get_node(
		"PatientValue"
	)

	encounter_label = case_content.get_node(
		"EncounterValue"
	)

	encounter_note = case_content.get_node(
		"EncounterNote"
	)

	var measurements: Node = content.get_node(
		"Measurements/Content"
	)

	hba1c_input = measurements.get_node(
		"HbA1cRow/HbA1cValue"
	)

	measurement_note = measurements.get_node(
		"MeasurementNote"
	)

	var actions: Node = content.get_node(
		"CaseActions/Content"
	)

	evaluate_button = actions.get_node(
		"EvaluateButton"
	)

	actions_note = actions.get_node(
		"ActionsNote"
	)

	http = HTTPRequest.new()
	http.timeout = 75.0
	add_child(http)

	encounter_menu = PopupMenu.new()
	encounter_menu.name = "EncounterMenu"
	encounter_button.add_child(encounter_menu)

	encounter_button.pressed.connect(
		_show_encounters
	)

	encounter_menu.id_pressed.connect(
		_on_encounter_selected
	)

	main.clinical_tooth_edit_requested.connect(
		_on_tooth_edit
	)

	main.clinical_undo_requested.connect(
		_undo
	)

	main.clinical_redo_requested.connect(
		_redo
	)

	main.clinical_reset_requested.connect(
		_reset
	)

	hba1c_input.value_changed.connect(
		_on_hba1c_changed
	)

	assessment.span_selection_changed.connect(
		_update_controls
	)
	
	assessment.span_selection_changed.connect(
		_sync_span_highlights
	)
	
	
	evaluate_button.pressed.connect(
		_evaluate
	)

	case_ready = false

	_update_controls()
	_set_status("Connecting to Python...")

	call_deferred("_initialize")


# --------------------------------------------------
# SMART desktop launch
# --------------------------------------------------

func _launch_code() -> String:
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--cdss-launch="):
			return argument.trim_prefix(
				"--cdss-launch="
			)

	return ""


func _initialize() -> void:
	var code: String = _launch_code()

	if code.is_empty():
		_set_status(
			"Development mode — no clinical case connected."
		)
		return

	var result: Dictionary = await _request(
		"/api/desktop/bootstrap",
		HTTPClient.METHOD_POST,
		{"code": code},
		false
	)

	if result.is_empty():
		return

	credential = str(
		result.get("desktop_session", "")
	)

	patient_id = str(
		result.get("patient", "")
	)

	if credential.is_empty():
		_error(
			"Python did not return a desktop credential."
		)
		return

	await refresh_patient()
	await refresh_encounters()
	await refresh_terminology()
	await refresh_media()
# --------------------------------------------------
# HTTP requests
# --------------------------------------------------

func _request(
	endpoint: String,
	method: int = HTTPClient.METHOD_GET,
	payload: Dictionary = {},
	authenticated: bool = true
) -> Dictionary:
	if busy:
		_error("Another backend request is active.")
		return {}

	if authenticated and credential.is_empty():
		_error("No active desktop session.")
		return {}

	busy = true
	_update_controls()

	var headers := PackedStringArray([
		"Accept: application/json",
		"Content-Type: application/json"
	])

	if authenticated:
		headers.append(
			SESSION_HEADER + ": " + credential
		)

	var body: String = ""

	if (
		method == HTTPClient.METHOD_POST
		or method == HTTPClient.METHOD_PATCH
	):
		body = JSON.stringify(payload)

	var start_error: Error = http.request(
		API_URL + endpoint,
		headers,
		method,
		body
	)

	if start_error != OK:
		busy = false
		_update_controls()

		_error(
			"Request could not start: "
			+ error_string(start_error)
		)
		return {}

	var completed: Array = await http.request_completed

	busy = false
	_update_controls()

	var transport: int = completed[0]
	var status: int = completed[1]

	if transport != HTTPRequest.RESULT_SUCCESS:
		_error(
			"Connection failed. Transport status: "
			+ str(transport)
		)
		return {}

	var response_body: PackedByteArray = completed[3]
	var response_text: String = (
		response_body.get_string_from_utf8()
	)

	var parsed: Variant = JSON.parse_string(
		response_text
	)

	if status == 401 and authenticated:
		credential = ""
		case_ready = false
		_update_controls()

	if status < 200 or status >= 300:
		var message: String = (
			"Backend HTTP " + str(status)
		)

		if parsed is Dictionary:
			message += ": " + str(
				parsed.get("detail", "Request rejected")
			)

		_error(message)
		return {}

	if not parsed is Dictionary:
		_error("Backend returned an invalid JSON object.")
		return {}

	return parsed

func refresh_terminology() -> void:
	var result: Dictionary = await _request(
		"/api/desktop/terminology"
	)

	var entries: Variant = result.get("terminology", [])

	if not entries is Array:
		_error("Invalid terminology response.")
		return

	terminology.clear()

	for entry in entries:
		if not entry is Dictionary:
			continue

		var code_system: String = str(
			entry.get("code_system", "")
		)
		var code: String = str(
			entry.get("code", "")
		)

		if code_system.is_empty() or code.is_empty():
			continue

		terminology[code_system + "|" + code] = entry
		
	assessment.terminology = terminology
	
	
# --------------------------------------------------
# Media catalogue
# --------------------------------------------------

func refresh_media() -> void:
	var result: Dictionary = await _request(
        "/api/desktop/media"
	)

	if result.is_empty():
		return

	var entries: Variant = result.get("media", null)

	if not entries is Array:
		_error("Invalid media catalogue response.")
		return

	var catalogue: Dictionary = {}

	for entry in entries:
		if not entry is Dictionary:
			continue

		var media_id: String = str(
			entry.get("media_id", "")
		)

		if media_id.is_empty():
			continue

		catalogue[media_id] = entry

	media_catalogue = catalogue
	media_loaded.emit(media_catalogue)
# --------------------------------------------------
# Patient information
# --------------------------------------------------

func refresh_patient() -> void:
	var result: Dictionary = await _request(
		"/api/desktop/patient"
	)

	if result.is_empty():
		_update_patient_label()
		return

	var name_value: Variant = result.get(
		"name", null
	)

	if name_value is String:
		if not name_value.is_empty():
			patient_display_name = name_value

	_update_patient_label()


func _update_patient_label() -> void:
	if patient_display_name.is_empty():
		patient_label.text = (
			"Patient: Name unavailable"
		)
	else:
		patient_label.text = (
			"Patient: " + patient_display_name
		)


# --------------------------------------------------
# Patient encounters
# --------------------------------------------------

func refresh_encounters() -> void:
	_set_status("Retrieving patient encounters...")

	var result: Dictionary = await _request(
		"/api/encounters"
	)

	if result.is_empty():
		return

	var entries: Variant = result.get(
		"encounters", []
	)

	if not entries is Array:
		_error("Invalid encounter list.")
		return

	encounters = entries
	encounter_menu.clear()

	for index in range(encounters.size()):
		if not encounters[index] is Dictionary:
			continue

		var encounter: Dictionary = encounters[index]

		encounter_menu.add_item(
			_encounter_description(encounter),
			index
		)

	if bool(result.get("has_next_page", false)):
		_set_status(
			"Only the first page of encounters "
			+ "is available from the current backend endpoint."
		)
	elif encounters.is_empty():
		_set_status("No encounters were returned.")
	else:
		_set_status(
			str(encounters.size())
			+ " encounter(s) available for selection."
		)

	_update_controls()


func _encounter_description(
	encounter: Dictionary
) -> String:
	var date_text: String = "Date unavailable"
	var type_text: String = "Clinical encounter"

	var period: Variant = encounter.get(
		"period", {}
	)

	if period is Dictionary:
		var start_date: String = str(
			period.get("start", "")
		)

		if start_date.length() >= 10:
			date_text = start_date.substr(0, 10)

	var encounter_types: Variant = encounter.get(
		"type", []
	)

	if encounter_types is Array:
		for entry in encounter_types:
			if not entry is Dictionary:
				continue

			var codings: Variant = entry.get(
				"coding", []
			)

			if not codings is Array:
				continue

			for coding in codings:
				if not coding is Dictionary:
					continue

				var display: String = str(
					coding.get("display", "")
				)

				if not display.is_empty():
					type_text = display
					break

	var status_text: String = str(
		encounter.get("status", "Unknown")
	)

	return (
		date_text + " — "
		+ type_text + " — "
		+ status_text
	)


func _update_encounter_label(
	encounter_id: String
) -> void:
	for item in encounters:
		if not item is Dictionary:
			continue

		if str(item.get("id", "")) == encounter_id:
			encounter_label.text = (
				"Encounter: "
				+ _encounter_description(item)
			)
			return

	encounter_label.text = (
		"Encounter details unavailable"
	)


func _show_encounters() -> void:
	if busy or credential.is_empty():
		return

	if encounters.is_empty():
		return

	var popup_position := Vector2i(
		encounter_button.get_screen_position()
		+ Vector2(0, encounter_button.size.y)
	)

	encounter_menu.popup(
		Rect2i(
			popup_position,
			Vector2i(440, 0)
		)
	)


func _on_encounter_selected(index: int) -> void:
	if index < 0 or index >= encounters.size():
		return

	if not encounters[index] is Dictionary:
		return

	var encounter: Dictionary = encounters[index]

	var encounter_id: String = str(
		encounter.get("id", "")
	)

	if encounter_id.is_empty():
		_error(
			"Encounter has no identifier."
		)
		return

	await open_encounter(encounter_id)


# --------------------------------------------------
# Open a working case
# --------------------------------------------------

func open_encounter(encounter_id: String) -> void:
	if busy:
		return

	case_ready = false
	current_case.clear()

	assessment.clear_case_spans()

	main.set_backend_history_actions(
		false, false, false
	)

	_update_controls()
	_set_status("Opening the selected clinical case...")

	var result: Dictionary = await _request(
		"/api/case/open",
		HTTPClient.METHOD_POST,
		{"encounter_id": encounter_id}
	)

	if result.is_empty():
		return

	await synchronize_case()


# --------------------------------------------------
# Authoritative case synchronization
# --------------------------------------------------

func synchronize_case() -> void:
	var result: Dictionary = await _request(
		"/api/desktop/case"
	)

	if result.is_empty():
		case_ready = false
		_update_controls()
		return

	if not result.get("teeth") is Dictionary:
		_error("Clinical case has no valid tooth states.")
		return

	_apply_case(result)
	await refresh_spans()


func _apply_case(data: Dictionary) -> void:
	var teeth: Dictionary = data["teeth"]
	var states: Dictionary = {}

	for tooth in teeth:
		var fdi: String = str(tooth)
		var status: String = str(teeth[tooth])

		match status:
			"present":
				states[fdi] = true
			"absent":
				states[fdi] = false
			_:
				_error(
					"Unexpected tooth status: "
					+ fdi + " = " + status
				)
				return

	main.initialize_tooth_case(states)

	current_case = data
	case_ready = true

	_update_patient_label()

	_update_encounter_label(
		str(data.get("encounter", ""))
	)

	var measurements: Variant = data.get(
		"measurements", {}
	)

	if measurements is Dictionary:
		var hba1c: Variant = measurements.get(
			"hba1c", null
		)

		if hba1c == null:
			# Preserve an empty measurement display.
			# No zero-valued clinical measurement is
			# constructed from missing FHIR data.
			hba1c_input.set_value_no_signal(0.0)
			hba1c_input.get_line_edit().text = ""

			measurement_note.text = (
				"HbA1c is not recorded in this encounter."
			)
		else:
			hba1c_input.set_value_no_signal(
				float(hba1c)
			)

			measurement_note.text = (
				"HbA1c: "
				+ str(hba1c)
				+ "% — current working-case value."
			)

	main.set_backend_history_actions(
		bool(data.get("can_undo", false)),
		bool(data.get("can_redo", false)),
		bool(data.get("can_reset", false))
	)

	_set_status(
		"Working case loaded. Revision "
		+ str(data.get("revision", ""))
	)

	_update_controls()
	case_loaded.emit(data)


# --------------------------------------------------
# Clinical editing
# --------------------------------------------------

func _on_tooth_edit(
	fdi: String,
	present: bool
) -> void:
	if not case_ready or busy:
		return

	await _change_case(
		"/api/case",
		HTTPClient.METHOD_PATCH,
		{
			"tooth": fdi,
			"state": "present" if present else "absent"
		}
	)


func _on_hba1c_changed(value: float) -> void:
	if not case_ready or busy:
		return

	var measurements: Dictionary = (
		current_case.get("measurements", {})
	)

	var old_value: Variant = measurements.get(
		"hba1c", null
	)

	if old_value != null:
		if is_equal_approx(
			float(old_value), value
		):
			return

	await _change_case(
		"/api/case",
		HTTPClient.METHOD_PATCH,
		{"hba1c": value}
	)


func _undo() -> void:
	if not case_ready or busy:
		return

	await _change_case(
		"/api/case/undo",
		HTTPClient.METHOD_POST
	)


func _redo() -> void:
	if not case_ready or busy:
		return

	await _change_case(
		"/api/case/redo",
		HTTPClient.METHOD_POST
	)


func _reset() -> void:
	if not case_ready or busy:
		return

	await _change_case(
		"/api/case/reset",
		HTTPClient.METHOD_POST
	)


func _change_case(
	endpoint: String,
	method: int,
	payload: Dictionary = {}
) -> void:
	if busy:
		return

	case_ready = false
	_update_controls()

	var _response: Dictionary = await _request(
		endpoint,
		method,
		payload
	)

	# Always fetch the actual current case instead
	# of reconstructing clinical history in Godot.
	if credential.is_empty():
		return

	await synchronize_case()


# --------------------------------------------------
# Missing-tooth span synchronization
# --------------------------------------------------

func refresh_spans() -> void:
	if not case_ready:
		return

	var result: Dictionary = await _request(
		"/api/case/spans"
	)

	if result.is_empty():
		return

	var selectable: Variant = result.get(
		"selectable_spans", null
	)

	var missing: Variant = result.get(
		"missing_spans", null
	)

	if not selectable is Array:
		_error("Invalid selectable spans.")
		return

	if not missing is Array:
		_error("Invalid missing spans.")
		return

	# Span presentation belongs to the assessment page.
	# It uses the existing anatomical tooth-name registry.
	assessment.set_case_spans(
		selectable,
		missing,
		main.tooth_controller
	)

	_update_controls()


# --------------------------------------------------
# Evaluation
# --------------------------------------------------

func _evaluate() -> void:
	if not case_ready or busy:
		return

	var selected: Array = (
		assessment.get_selected_spans()
	)

	if selected.is_empty():
		_set_status("Select a missing-tooth span.")
		return

	var selection_result: Dictionary = await _request(
		"/api/case/select-spans",
		HTTPClient.METHOD_POST,
		{"spans": selected}
	)

	if selection_result.is_empty():
		return

	var supported: Variant = selection_result.get(
		"selected_spans", []
	)

	var unsupported: Variant = selection_result.get(
		"unsupported_spans", []
	)

	if unsupported is Array and not unsupported.is_empty():
		assessment.unsupported_note.text = (
			"Some selected multi-tooth spans are not "
			+ "supported by the current GDL2 demonstration."
		)

	if not supported is Array or supported.is_empty():
		_set_status(
			"No selected spans are supported "
			+ "by the current clinical ruleset."
		)
		return

	_set_status(
		"Evaluating selected treatment alternatives..."
	)

	var evaluation: Dictionary = await _request(
		"/api/case/evaluate",
		HTTPClient.METHOD_POST
	)

	if evaluation.is_empty():
		return

	actions_note.text = (
		"Clinical evaluation completed."
	)

	evaluation_completed.emit(evaluation)


# --------------------------------------------------
# Interface availability
# --------------------------------------------------


func _update_controls() -> void:
	if encounter_button != null:
		encounter_button.disabled = (
			busy
			or credential.is_empty()
			or encounters.is_empty()
		)

	if hba1c_input != null:
		hba1c_input.editable = (
			case_ready and not busy
		)

	if evaluate_button != null and assessment != null:
		evaluate_button.disabled = (
			not case_ready
			or busy
			or assessment.get_selected_spans().is_empty()
		)

	if main != null:
		if busy or not case_ready:
			main.set_backend_history_actions(
				false, false, false
			)
		elif not current_case.is_empty():
			main.set_backend_history_actions(
				bool(current_case.get("can_undo", false)),
				bool(current_case.get("can_redo", false)),
				bool(current_case.get("can_reset", false))
			)

	# Workflow emphasis is independent of clinical history.
	if (
		assessment != null
		and encounter_button != null
		and evaluate_button != null
	):
		assessment.set_workflow_emphasis(
			case_ready,
			not encounter_button.disabled,
			not assessment.get_selected_spans().is_empty(),
			not evaluate_button.disabled,
			busy
		)


func _set_status(message: String) -> void:
	if encounter_note != null:
		encounter_note.text = message


func _error(message: String) -> void:
	_set_status(message)
	connection_error.emit(message)
	push_warning(message)
