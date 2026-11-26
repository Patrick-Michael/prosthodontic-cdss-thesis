
extends VBoxContainer

signal comparison_mode_changed(enabled: bool)
signal treatment_selected(treatment_code: String)

const BLUE := Color("#294D79")
const ACTIVE := Color("#2868C9")
const SURFACE := Color("#253346")
const DARK := Color("#1B2939")
const BORDER := Color("#405168")
const TEXT := Color("#E5EDF7")
const MUTED := Color("#B9C7D8")
const CAUTION := Color("#F0CE83")
const AVAILABLE := Color("#A8E0CE")
const EXCLUDED := Color("#F1C1B4")

var evaluation_data: Dictionary = {}
var evaluated_spans: Array = []
var tooth_controller: Node3D

var selected_span_index: int = 0
var selected_category: String = "available"

var comparison_mode: bool = false
var detail_open: bool = false
var detail_entry: Dictionary = {}

var span_selector: OptionButton
var category_buttons: Dictionary = {}
var comparison_button: Button

var overview_controls: VBoxContainer
var body_scroll: ScrollContainer
var body: VBoxContainer
var popup: AcceptDialog

var comparison_target: VBoxContainer
var comparison_scroll: ScrollContainer
var media_catalogue: Dictionary = {}

# --------------------------------------------------
# Initialization
# --------------------------------------------------
func set_media_catalogue(catalogue: Dictionary) -> void:
	media_catalogue = catalogue.duplicate(true)
	
func _ready() -> void:
	var placeholder := get_node_or_null(
		"TreatmentComparisonPagePlaceholder"
	)

	if placeholder != null:
		placeholder.hide()

	var old_cards := get_node_or_null(
		"TreatmentCardList"
	)

	if old_cards != null:
		old_cards.hide()

	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	size_flags_vertical = Control.SIZE_EXPAND_FILL

	add_theme_constant_override("separation", 8)

	_build_page()
	_render()


func _build_page() -> void:
	# Controls remain outside the scrolling card content.
	overview_controls = VBoxContainer.new()
	overview_controls.name = "OverviewControls"
	overview_controls.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)
	overview_controls.add_theme_constant_override(
		"separation", 10
	)
	add_child(overview_controls)
	move_child(overview_controls, 0)

	_build_span_selector()
	_build_category_selector()
	_build_comparison_action()

	body_scroll = ScrollContainer.new()
	body_scroll.name = "TreatmentBodyScroll"
	body_scroll.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)
	body_scroll.size_flags_vertical = (
		Control.SIZE_EXPAND_FILL
	)
	body_scroll.horizontal_scroll_mode = (
		ScrollContainer.SCROLL_MODE_DISABLED
	)
	body_scroll.vertical_scroll_mode = (
		ScrollContainer.SCROLL_MODE_AUTO
	)
	add_child(body_scroll)
	move_child(body_scroll, 1)

	var margin := MarginContainer.new()
	margin.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)
	margin.add_theme_constant_override("margin_left", 8)
	margin.add_theme_constant_override("margin_right", 16)
	margin.add_theme_constant_override("margin_top", 4)
	margin.add_theme_constant_override("margin_bottom", 10)
	body_scroll.add_child(margin)

	body = VBoxContainer.new()
	body.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)
	body.add_theme_constant_override("separation", 8)
	margin.add_child(body)

	popup = AcceptDialog.new()
	popup.title = "Information"
	popup.dialog_autowrap = true
	popup.min_size = Vector2i(430, 220)
	add_child(popup)


# --------------------------------------------------
# Evaluated span
# --------------------------------------------------

func _build_span_selector() -> void:
	var panel := _panel(overview_controls, DARK)
	var content := VBoxContainer.new()
	content.add_theme_constant_override("separation", 5)
	panel.add_child(content)

	_add_label(
		content,
		"EVALUATED SPAN",
		11,
		MUTED
	)

	span_selector = OptionButton.new()
	span_selector.custom_minimum_size.y = 34
	span_selector.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)
	span_selector.add_theme_font_size_override(
		"font_size", 12
	)
	span_selector.item_selected.connect(
		_on_span_selected
	)
	content.add_child(span_selector)


# --------------------------------------------------
# Category controls
# --------------------------------------------------

func _build_category_selector() -> void:
	var heading_row := HBoxContainer.new()
	heading_row.add_theme_constant_override(
		"separation", 6
	)
	overview_controls.add_child(heading_row)

	var title := _add_label(
		heading_row,
		"Treatment options",
		16,
		TEXT
	)
	title.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)

	var help := Button.new()
	help.text = "?"
	help.custom_minimum_size = Vector2(26, 26)
	help.pressed.connect(
		_show_popup.bind(
			"Treatment classifications",
			"Available and Excluded describe the "
			+ "clinical rule evaluation.\n\n"
			+ "No intervention is presented separately "
			+ "because it is not rule-evaluated.\n\n"
			+ "Treatment alternatives are not ranked."
		)
	)
	heading_row.add_child(help)

	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 5)
	overview_controls.add_child(row)

	for category in [
		"available",
		"excluded",
		"no_intervention"
	]:
		var button := Button.new()
		button.custom_minimum_size.y = 35
		button.size_flags_horizontal = (
			Control.SIZE_EXPAND_FILL
		)
		button.add_theme_font_size_override(
			"font_size", 11
		)
		button.pressed.connect(
			_select_category.bind(category)
		)
		row.add_child(button)
		category_buttons[category] = button


# --------------------------------------------------
# Comparison overlay action
# --------------------------------------------------

func _build_comparison_action() -> void:
	comparison_button = Button.new()
	comparison_button.text = "Open comparison view"
	comparison_button.custom_minimum_size.y = 35
	comparison_button.add_theme_font_size_override(
		"font_size", 12
	)
	comparison_button.pressed.connect(
		_open_comparison
	)
	overview_controls.add_child(comparison_button)
	_style_action(comparison_button, true)


func _open_comparison() -> void:
	if evaluated_spans.is_empty():
		return

	if detail_open:
		detail_open = false
		detail_entry.clear()

	comparison_mode = true
	_render_comparison()

	comparison_mode_changed.emit(true)


func close_comparison() -> void:
	comparison_mode = false
	comparison_mode_changed.emit(false)


# --------------------------------------------------
# External overlay connection
# --------------------------------------------------

func set_comparison_target(
	target: VBoxContainer
) -> void:
	comparison_target = target
	comparison_target.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)
	comparison_target.size_flags_vertical = (
		Control.SIZE_EXPAND_FILL
	)
	comparison_target.add_theme_constant_override(
		"separation", 8
	)

	if comparison_mode:
		_render_comparison()


# --------------------------------------------------
# Evaluation response
# --------------------------------------------------

func display_evaluation(
	data: Dictionary,
	controller: Node3D
) -> bool:
	var raw: Variant = data.get("results", null)

	if not raw is Array:
		return false

	var entries: Array = []

	for item in raw:
		if not item is Dictionary:
			continue

		if not item.get("span") is Array:
			continue

		var evaluation: Variant = item.get(
			"evaluation", null
		)

		if not evaluation is Dictionary:
			continue

		if not evaluation.get("treatments") is Array:
			continue

		var knowledge: Variant = evaluation.get(
			"knowledge", null
		)

		if not knowledge is Dictionary:
			continue

		if not knowledge.get("treatments") is Array:
			continue

		entries.append(item)

	if entries.is_empty():
		return false

	evaluation_data = data.duplicate(true)
	evaluated_spans = entries
	tooth_controller = controller

	selected_span_index = 0
	selected_category = "available"
	detail_open = false
	detail_entry.clear()
	comparison_mode = false

	span_selector.clear()

	for entry in evaluated_spans:
		var names: PackedStringArray = []
		var identifiers: PackedStringArray = []

		for fdi_value in entry["span"]:
			var fdi := str(fdi_value)
			identifiers.append(fdi)

			var tooth_name := ""

			if tooth_controller != null:
				tooth_name = str(
					tooth_controller.get_tooth_name(fdi)
				)

			names.append(
				tooth_name.capitalize()
				if not tooth_name.is_empty()
				else "Tooth " + fdi
			)

		span_selector.add_item(
			", ".join(names)
			+ " (FDI "
			+ ", ".join(identifiers)
			+ ")"
		)

	span_selector.select(0)
	_render()
	return true


func clear_evaluation() -> void:
	evaluation_data.clear()
	evaluated_spans.clear()
	detail_entry.clear()

	selected_span_index = 0
	selected_category = "available"
	detail_open = false

	span_selector.clear()

	if comparison_mode:
		close_comparison()

	_render()

	if comparison_target != null:
		_clear_children(comparison_target)
		
	if tooth_controller != null:
		tooth_controller.clear_abutment_highlights()

# --------------------------------------------------
# Navigation
# --------------------------------------------------

func _on_span_selected(index: int) -> void:
	if index < 0 or index >= evaluated_spans.size():
		return

	selected_span_index = index
	detail_open = false
	detail_entry.clear()

	_render()

	if comparison_mode:
		_render_comparison()


func _select_category(category: String) -> void:
	selected_category = category
	detail_open = false
	detail_entry.clear()

	_render()


# --------------------------------------------------
# Backend data lookup
# --------------------------------------------------

func _current_evaluation() -> Dictionary:
	if (
		selected_span_index < 0
		or selected_span_index >= evaluated_spans.size()
	):
		return {}

	return evaluated_spans[
		selected_span_index
	].get("evaluation", {})


func _current_knowledge() -> Array:
	return _current_evaluation().get(
		"knowledge", {}
	).get("treatments", [])


func _find_knowledge(code: String) -> Dictionary:
	for record in _current_knowledge():
		if not record is Dictionary:
			continue

		if str(
			record.get("treatment_code", "")
		) == code:
			return record

	return {}


func _no_intervention_entry() -> Dictionary:
	for record in _current_knowledge():
		if not record is Dictionary:
			continue

		if (
			record.get("treatment_code") == null
			and record.get("guideline_id") == null
		):
			return {
				"record": record,
				"outcome": {},
				"code": ""
			}

	return {}


func _outcome_entries() -> Array:
	var result: Array = []

	for outcome in _current_evaluation().get(
		"treatments", []
	):
		if not outcome is Dictionary:
			continue

		var treatment: Variant = outcome.get(
			"treatment", {}
		)

		if not treatment is Dictionary:
			continue

		var code := str(
			treatment.get("code", "")
		)

		var record := _find_knowledge(code)

		if record.is_empty():
			push_warning(
				"Missing knowledge record for treatment: "
				+ code
			)
			continue

		result.append({
			"record": record,
			"outcome": outcome,
			"code": code
		})

	return result


func _visible_entries() -> Array:
	if selected_category == "no_intervention":
		var record := _no_intervention_entry()

		if record.is_empty():
			return []

		return [record]

	var result: Array = []

	for entry in _outcome_entries():
		var status := str(
			entry["outcome"].get("status", "")
		)

		if (
			selected_category == "available"
			and status in ["Available", "Caution"]
		):
			result.append(entry)

		elif (
			selected_category == "excluded"
			and status == "Excluded"
		):
			result.append(entry)

	return result



func _comparison_entries() -> Array:
	var result: Array = []

	# Include only treatments that the clinical
	# inference engine has classified as available.
	# Treatments with soft alerts remain included.
	for entry in _outcome_entries():
		var outcome: Dictionary = entry["outcome"]

		var status: String = str(
			outcome.get("status", "")
		)

		if status in ["Available", "Caution"]:
			result.append(entry)

	# No intervention is an independent alternative,
	# not a rule-evaluated available treatment.
	var no_intervention := _no_intervention_entry()

	if not no_intervention.is_empty():
		result.append(no_intervention)

	return result



# --------------------------------------------------
# Main card view
# --------------------------------------------------

func _render() -> void:
	if body == null:
		return

	_clear_children(body)
	overview_controls.visible = not detail_open

	_update_categories()

	if evaluated_spans.is_empty():
		_add_label(
			body,
			"No evaluation loaded.",
			12,
			MUTED,
			true
		)
		return

	if detail_open:
		_render_detail()
	else:
		_render_cards()

	body_scroll.scroll_vertical = 0


func _update_categories() -> void:
	var available_count := 0
	var excluded_count := 0

	for entry in _outcome_entries():
		var status := str(
			entry["outcome"].get("status", "")
		)

		if status in ["Available", "Caution"]:
			available_count += 1
		elif status == "Excluded":
			excluded_count += 1

	category_buttons["available"].text = (
		"Available (" + str(available_count) + ")"
	)

	category_buttons["excluded"].text = (
		"Excluded (" + str(excluded_count) + ")"
	)

	category_buttons["no_intervention"].text = (
		"No intervention"
	)

	for category in category_buttons:
		_style_action(
			category_buttons[category],
			selected_category == category
		)


func _render_cards() -> void:
	var entries := _visible_entries()

	if entries.is_empty():
		_add_label(
			body,
			"No options returned for this category.",
			12,
			MUTED,
			true
		)
		return

	for entry in entries:
		_add_treatment_card(body, entry)



func _add_treatment_card(
	parent: Node,
	entry: Dictionary
) -> void:
	var record: Dictionary = entry["record"]
	var outcome: Dictionary = entry["outcome"]

	var card := _panel(parent, SURFACE)

	var stack := VBoxContainer.new()
	stack.add_theme_constant_override(
		"separation", 7
	)
	card.add_child(stack)

	var name := _add_label(
		stack,
		str(record.get("name", "")),
		14,
		TEXT,
		true
	)

	name.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)

	var status_row := HBoxContainer.new()
	status_row.add_theme_constant_override(
		"separation", 6
	)
	stack.add_child(status_row)

	var status := _add_label(
		status_row,
		_status(entry),
		11,
		_status_color(entry)
	)

	status.autowrap_mode = TextServer.AUTOWRAP_OFF
	status.clip_text = false

	var spacer := Control.new()
	spacer.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)
	status_row.add_child(spacer)

	var alerts: Array = outcome.get(
		"soft_alerts", []
	)

	if not alerts.is_empty():
		_add_label(
			status_row,
			"Clinical caution",
			11,
			CAUTION
		)

		var caution_help := Button.new()
		caution_help.text = "?"
		caution_help.tooltip_text = (
			"Read clinical caution"
		)
		caution_help.custom_minimum_size = (
			Vector2(26, 26)
		)
		caution_help.add_theme_font_size_override(
			"font_size", 11
		)
		caution_help.add_theme_color_override(
			"font_color", CAUTION
		)

		caution_help.pressed.connect(
			_show_card_cautions.bind(entry)
		)

		status_row.add_child(caution_help)

	var summary := _text(
		record.get("summary")
	)

	if not summary.is_empty():
		_add_label(
			stack,
			summary,
			12,
			MUTED,
			true
		)

	var explore := Button.new()
	explore.text = "Explore treatment"
	explore.custom_minimum_size.y = 32
	explore.add_theme_font_size_override(
		"font_size", 12
	)
	explore.pressed.connect(
		_open_detail.bind(entry)
	)
	stack.add_child(explore)



# --------------------------------------------------
# Full-width comparison overlay
# --------------------------------------------------

func _render_comparison() -> void:
	if comparison_target == null:
		return

	_clear_children(comparison_target)

	var entries := _comparison_entries()

	if entries.is_empty():
		_add_label(
			comparison_target,
			"No treatment knowledge returned.",
			12,
			MUTED,
			true
		)
		return

	var subtitle := ""

	if selected_span_index < span_selector.item_count:
		subtitle = span_selector.get_item_text(
			selected_span_index
		)

	_add_label(
		comparison_target,
		subtitle,
		12,
		MUTED,
		true
	)

	_add_label(
		comparison_target,
		"All evaluated alternatives are displayed "
		+ "without ranking.",
		11,
		MUTED,
		true
	)

	comparison_scroll = ScrollContainer.new()
	comparison_scroll.name = "ComparisonMatrixScroll"
	comparison_scroll.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)
	comparison_scroll.size_flags_vertical = (
		Control.SIZE_EXPAND_FILL
	)
	comparison_scroll.horizontal_scroll_mode = (
		ScrollContainer.SCROLL_MODE_AUTO
	)
	comparison_scroll.vertical_scroll_mode = (
		ScrollContainer.SCROLL_MODE_AUTO
	)
	comparison_target.add_child(comparison_scroll)

	var matrix := GridContainer.new()
	matrix.name = "ComparisonMatrix"
	matrix.columns = entries.size() + 1
	matrix.add_theme_constant_override(
		"h_separation", 4
	)
	matrix.add_theme_constant_override(
		"v_separation", 4
	)
	comparison_scroll.add_child(matrix)

	# Treatment columns.
	_matrix_cell(
		matrix,
		"Characteristic",
		true,
		165
	)

	for entry in entries:
		_matrix_cell(
			matrix,
			str(
				entry["record"].get("name", "")
			),
			true,
			210
		)

	# SQLite treatment characteristics.
	for label in _attribute_labels(entries):
		_matrix_cell(
			matrix,
			label,
			true,
			165
		)

		for entry in entries:
			_matrix_cell(
				matrix,
				_attribute_value(
					entry["record"],
					label
				),
				false,
				210
			)

	
	# Clinical evaluation status.
	_matrix_cell(
		matrix,
		"Clinical status",
		true,
		165
	)

	for entry in entries:
		var outcome: Dictionary = entry["outcome"]
		var status_text: String = _status(entry)

		var status_cell := _panel(matrix, SURFACE)
		status_cell.custom_minimum_size.x = 210

		var status_content := VBoxContainer.new()
		status_content.add_theme_constant_override(
			"separation", 5
		)
		status_cell.add_child(status_content)

		var status_label := _add_label(
			status_content,
			status_text,
			12,
			_status_color(entry),
			true
		)

		status_label.autowrap_mode = (
			TextServer.AUTOWRAP_OFF
		)

		var alerts: Array = outcome.get(
			"soft_alerts", []
		)

		if not alerts.is_empty():
			var caution_row := HBoxContainer.new()
			caution_row.add_theme_constant_override(
				"separation", 5
			)
			status_content.add_child(caution_row)

			_add_label(
				caution_row,
				"Clinical caution",
				11,
				CAUTION
			)

			var help_button := Button.new()
			help_button.text = "?"
			help_button.tooltip_text = (
				"Read clinical caution"
			)
			help_button.custom_minimum_size = (
				Vector2(24, 24)
			)
			help_button.add_theme_font_size_override(
				"font_size", 11
			)
			help_button.add_theme_color_override(
				"font_color", CAUTION
			)

			help_button.pressed.connect(
				_show_card_cautions.bind(entry)
			)

			caution_row.add_child(help_button)


	# Detail buttons.
	_matrix_cell(
		matrix,
		"Further information",
		true,
		165
	)

	for entry in entries:
		var holder := _panel(
			matrix,
			SURFACE
		)
		holder.custom_minimum_size.x = 210

		var button := Button.new()
		button.text = "Explore treatment"
		button.custom_minimum_size.y = 32
		button.add_theme_font_size_override(
			"font_size", 11
		)
		button.pressed.connect(
			_open_detail.bind(entry)
		)
		holder.add_child(button)


func _attribute_labels(entries: Array) -> Array:
	var labels: Array = []

	for entry in entries:
		for attribute in entry["record"].get(
			"attributes", []
		):
			if not attribute is Dictionary:
				continue

			var label := str(
				attribute.get("label", "")
			)

			if (
				not label.is_empty()
				and not labels.has(label)
			):
				labels.append(label)

	return labels


func _attribute_value(
	record: Dictionary,
	label: String
) -> String:
	for attribute in record.get(
		"attributes", []
	):
		if not attribute is Dictionary:
			continue

		if str(
			attribute.get("label", "")
		) == label:
			var value := _text(
				attribute.get("display_value")
			)

			return (
				value
				if not value.is_empty()
				else "Not provided"
			)

	return "Not provided"


func _matrix_cell(
	parent: GridContainer,
	value: String,
	header: bool,
	width: float
) -> void:
	var panel := _panel(
		parent,
		BLUE if header else SURFACE
	)

	panel.custom_minimum_size.x = width

	var label := _add_label(
		panel,
		value,
		12,
		TEXT if header else MUTED,
		true
	)
	label.vertical_alignment = (
		VERTICAL_ALIGNMENT_CENTER
	)


func _get_input_value(element_id: String) -> Variant:
	var explanations: Dictionary = (
		_current_evaluation().get("explanations", {})
	)

	for item in explanations.get("inputs", []):
		if item is Dictionary:
			if str(item.get("element_id", "")) == element_id:
				return item.get("value")

	return null


func _resolve_abutments(entry: Dictionary) -> Array:
	var result: Array = []

	var outcome: Dictionary = entry.get("outcome", {})
	if str(outcome.get("status", "")) != "Available":
		return result

	var span: Array = evaluated_spans[
		selected_span_index
	].get("span", [])

	if span.size() != 1:
		return result

	var target: String = str(span[0])

	if target.length() != 2:
		return result

	var quadrant: int = int(target.substr(0, 1))
	var position: int = int(target.substr(1, 1))

	if quadrant < 1 or quadrant > 4:
		return result

	if position < 1 or position > 8:
		return result

	var code: String = str(entry.get("code", ""))

	match code:
		"at0003":
			if _get_input_value("gt0008") == true:
				var mesial := str(quadrant) + str(position - 1)
				if tooth_controller.is_tooth_present(mesial):
					result.append(mesial)

			if _get_input_value("gt0009") == true:
				var distal := str(quadrant) + str(position + 1)
				if tooth_controller.is_tooth_present(distal):
					result.append(distal)

		"at0006":
			var count_value: Variant = _get_input_value("gt0010")
			if count_value == null:
				return result

			var count: int = mini(int(count_value), 2)

			for number in range(position + 1, 9):
				if result.size() >= count:
					break

				var distal := str(quadrant) + str(number)

				if tooth_controller.is_tooth_present(distal):
					result.append(distal)

	return result

# --------------------------------------------------
# Treatment detail view
# --------------------------------------------------

func _open_detail(entry: Dictionary) -> void:
	detail_entry = entry
	detail_open = true

	if comparison_mode:
		close_comparison()

	_render()

	treatment_selected.emit(
		str(entry.get("code", ""))
	)
	
	if tooth_controller != null:
		tooth_controller.set_highlighted_abutments(
			_resolve_abutments(entry)
		)

func _render_detail() -> void:
	if detail_entry.is_empty():
		return

	var record: Dictionary = detail_entry["record"]
	var outcome: Dictionary = detail_entry["outcome"]
	var code := str(detail_entry.get("code", ""))

	var back := Button.new()
	back.text = "Back to treatment options"
	back.alignment = (
		HORIZONTAL_ALIGNMENT_LEFT
	)
	back.custom_minimum_size.y = 32
	back.pressed.connect(
		_return_from_detail
	)
	body.add_child(back)

	var header := _panel(body, BLUE)
	var header_content := VBoxContainer.new()
	header_content.add_theme_constant_override(
		"separation", 5
	)
	header.add_child(header_content)

	_add_label(
		header_content,
		str(record.get("name", "")),
		16,
		TEXT,
		true
	)

	
	var status_row := HBoxContainer.new()
	status_row.add_theme_constant_override(
		"separation", 10
)
	status_row.alignment = BoxContainer.ALIGNMENT_BEGIN
	header_content.add_child(status_row)

	_add_label(
		status_row,
		_status(detail_entry),
		11,
		_status_color(detail_entry)
	)

	var alerts: Array = outcome.get(
		"soft_alerts", []
	)

	if not alerts.is_empty():
		_add_label(
			status_row,
			"Clinical caution",
			11,
			CAUTION
		)

		var caution_help := Button.new()
		caution_help.text = "?"
		caution_help.tooltip_text = "Read clinical caution"
		caution_help.custom_minimum_size = Vector2(26, 26)
		caution_help.add_theme_font_size_override(
		"font_size", 11
		)
		caution_help.add_theme_color_override(
		"font_color", CAUTION
	)

		caution_help.pressed.connect(
			_show_card_cautions.bind(detail_entry)
	)
		status_row.add_child(caution_help)
			
	var summary := _text(
		record.get("summary")
	)

	if not summary.is_empty():
		_add_label(
			body,
			summary,
			12,
			MUTED,
			true
		)

	_render_patient_information(record)

	if not code.is_empty():
		_render_rule_explanations(
			code,
			outcome
		)
		_render_clinical_inputs(code)

	_render_practitioner_information(record)
	_render_procedures(record)


func _return_from_detail() -> void:
	if tooth_controller != null:
		tooth_controller.clear_abutment_highlights()

	detail_open = false
	detail_entry.clear()
	_render()


# --------------------------------------------------
# Patient-facing explanation
# --------------------------------------------------

func _render_patient_information(
	record: Dictionary
) -> void:
	var content := _section(
		body,
		"Understanding this option"
	)

	var explanation := _text(
		record.get("explanation")
	)

	if not explanation.is_empty():
		_add_label(
			content,
			explanation,
			12,
			MUTED,
			true
		)

	for attribute in record.get(
		"attributes", []
	):
		if not attribute is Dictionary:
			continue

		var row := HBoxContainer.new()
		row.add_theme_constant_override(
			"separation", 6
		)
		content.add_child(row)

		var name := str(
			attribute.get("label", "")
		)

		var value := _text(
			attribute.get("display_value")
		)

		var label := RichTextLabel.new()
		
		var label_style := StyleBoxFlat.new()
		label_style.bg_color = Color.TRANSPARENT
		label_style.content_margin_left = 10
		label_style.content_margin_right = 6
		label_style.content_margin_top = 3
		label_style.content_margin_bottom = 3

		label.add_theme_stylebox_override(
			"normal",
			label_style
		)
		
		label.fit_content = true
		label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		label.scroll_active = false
		label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		label.add_theme_font_size_override("bold_font_size", 12)
		label.add_theme_font_size_override(
			"normal_font_size", 12
)
		label.add_theme_color_override(
			"default_color", TEXT
)

		label.push_bold()
		label.add_text(name + ": ")
		label.pop()

		label.add_text(value)

		row.add_child(label)

		var help_text := _join_existing([
			attribute.get(
				"attribute_explanation"
			),
			attribute.get("explanation")
		])

		if not help_text.is_empty():
			var help := Button.new()
			help.text = "?"
			help.pressed.connect(
				_show_popup.bind(
					name,
					help_text
				)
			)
			row.add_child(help)


# --------------------------------------------------
# Rule explanations and cautions
# --------------------------------------------------

func _render_rule_explanations(
	code: String,
	outcome: Dictionary
) -> void:
	var evaluation := _current_evaluation()
	var explanations: Dictionary = evaluation.get(
		"explanations", {}
	)

	var excluded := (
		str(outcome.get("status", "")) == "Excluded"
	)

	var key := "why"

	var content := _collapsible(
		body,
		"Why not?" if excluded else "Why this result?"
	)

	var matching: Array = []
	
	var final_status := str(
		outcome.get("status", "")
	)

	for rule in explanations.get(key, []):
		if not rule is Dictionary:
			continue
		if str(rule.get("status", "")) != final_status:
			continue

		var treatment: Variant = rule.get(
			"treatment", {}
		)

		if (
			treatment is Dictionary
			and str(
				treatment.get("code", "")
			) == code
		):
			matching.append(rule)

	if matching.is_empty():
		_add_label(
			content,
			"No matching rule explanation was returned.",
			12,
			MUTED,
			true
		)

	var rule_details: Dictionary = evaluation.get(
		"knowledge", {}
	).get("rule_details", {})

	for rule in matching:
		var label := _text(rule.get("label"))
		var description := _text(
			rule.get("description")
		)

		if not label.is_empty():
			_add_label(content, label, 13)

		if not description.is_empty():
			_add_label(
				content,
				description,
				12,
				MUTED,
				true
			)

		var rule_id := str(
			rule.get("rule_id", "")
		)

		var details: Variant = rule_details.get(
			rule_id, {}
		)

		if details is Dictionary:
			for field in [
				"clinical_detail",
				"limitations"
			]:
				var value := _text(
					details.get(field)
				)

				if not value.is_empty():
					_add_label(
						content,
						field.replace(
							"_", " "
						).capitalize()
						+ ": " + value,
						11,
						MUTED,
						true
					)

	

# --------------------------------------------------
# Clinical inputs used by inference
# --------------------------------------------------


# --------------------------------------------------
# Clinical inputs used by inference
# --------------------------------------------------

func _render_clinical_inputs(
	code: String
) -> void:
	var explanations: Dictionary = (
		_current_evaluation().get(
			"explanations", {}
		)
	)

	var content := _collapsible(
		body,
		"Clinical inputs used in this evaluation"
	)

	var relevant: Array = []

	for item in explanations.get("inputs", []):
		if not item is Dictionary:
			continue

		for link in item.get("related_rules", []):
			if not link is Dictionary:
				continue

			var treatment: Variant = link.get(
				"treatment", {}
			)

			if (
				treatment is Dictionary
				and str(
					treatment.get("code", "")
				) == code
			):
				relevant.append(item)
				break

	for item in relevant:
		var line := (
			str(item.get("label", ""))
			+ ": "
			+ _text(item.get("value"))
		)

		var unit := _text(item.get("unit"))

		if not unit.is_empty():
			line += " " + unit

		_add_label(
			content,
			line,
			12,
			TEXT,
			true
		)

		var description := _text(
			item.get("description")
		)

		if not description.is_empty():
			_add_label(
				content,
				description,
				11,
				MUTED,
				true
			)

	if relevant.is_empty():
		_add_label(
			content,
			"No related input descriptions returned.",
			12,
			MUTED,
			true
		)

	# Add anatomical identification of supporting teeth.
	# This supplements the inference inputs without
	# modifying or recalculating clinical results.

	if code in ["at0003", "at0006"]:
		_render_supporting_teeth(content, code)


# --------------------------------------------------
# Anatomical identification of supporting teeth
# --------------------------------------------------

func _render_supporting_teeth(
	content: Control,
	code: String
) -> void:
	if tooth_controller == null:
		return

	if detail_entry.is_empty():
		return

	# Reuse the same resolver used for the 3D
	# abutment highlights.

	var support_teeth: Array = (
		_resolve_abutments(detail_entry)
	)

	if support_teeth.is_empty():
		return

	_add_label(
		content,
		"Proposed supporting teeth:",
		12,
		TEXT,
		true
	)

	var target := ""

	var span: Array = evaluated_spans[
		selected_span_index
	].get("span", [])

	if span.size() == 1:
		target = str(span[0])

	var target_position := -1

	if target.length() == 2:
		target_position = int(
			target.substr(1, 1)
		)

	for tooth in support_teeth:
		var fdi := str(tooth)

		var name := str(
			tooth_controller.get_tooth_name(fdi)
		)

		var position := int(
			fdi.substr(1, 1)
		)

		var description := ""

		if code == "at0003":
			if position < target_position:
				description = "Mesial abutment"
			elif position > target_position:
				description = "Distal abutment"
			else:
				description = "Abutment"

		elif code == "at0006":
			description = "Distal supporting tooth"

		var line := (
			description
			+ ": FDI "
			+ fdi
		)

		if not name.is_empty():
			line += " (" + name + ")"

		_add_label(
			content,
			line,
			11,
			MUTED,
			true
		)

	# The inference count and the teeth available
	# in the 3D odontogram are not necessarily
	# identical. Report that difference explicitly
	# instead of inventing anatomical identities.

	
				



# --------------------------------------------------
# Practitioner information
# --------------------------------------------------

func _render_practitioner_information(
	record: Dictionary
) -> void:
	var text_value := _text(
		record.get("clinical_detail")
	)

	if text_value.is_empty():
		return

	var content := _collapsible(
		body,
		"Practitioner information"
	)

	_add_label(
		content,
		text_value,
		12,
		MUTED,
		true
	)


# --------------------------------------------------
# Procedure and maintenance brochures
# --------------------------------------------------

# Frontend association of clinical step IDs with media IDs.
# Add the actual IDs from the knowledge database here.
const STEP_MEDIA: Dictionary = {
	# Conventional fixed dental bridge
	"fdp_01": "img_07",
	"fdp_02": "img_02",
	"fdp_03": "img_06",

	# Cantilever fixed dental bridge
	"cantilever_01": "img_07",
	"cantilever_02": "img_02",
	"cantilever_03": "img_03",

	# Implant-supported crown
	"implant_01": "img_13",
	"implant_03": "img_09",

	# Removable partial denture
	"rpd_01": "img_02",
	"rpd_02": "img_01",

	# No intervention: possible changes
	"no_intervention_01": "img_08",
	"no_intervention_02": "img_08",

	# Fixed bridge maintenance
	"bridge_care_01": "img_12",
	"bridge_care_02": "img_10",

	# Implant maintenance
	"implant_care_01": "img_12",
	"implant_care_02": "img_11",

	# Removable partial denture maintenance
	"rpd_care_01": "img_05",
	"rpd_care_02": "img_12",

	# No intervention: ongoing care
	"no_intervention_care_01": "img_12"
}

func get_step_media_id(step_id: String) -> String:
	return str(STEP_MEDIA.get(step_id, ""))

func _render_procedures(record: Dictionary) -> void:
	var procedures: Array = record.get("procedures", [])

	if procedures.is_empty():
		return

	for category in ["treatment", "maintenance"]:
		var matching: Array = []

		for procedure in procedures:
			if not procedure is Dictionary:
				continue

			if str(procedure.get("procedure_type", "")) == category:
				matching.append(procedure)

		if matching.is_empty():
			continue

		var title := (
            "Procedure information"
			if category == "treatment"
			else "Maintenance information"
		)

		var button := Button.new()
		button.text = title + "  ▸"
		button.alignment = HORIZONTAL_ALIGNMENT_LEFT
		button.custom_minimum_size.y = 40
		button.add_theme_font_size_override("font_size", 12)

		button.pressed.connect(
			_open_brochure.bind(record, matching, title)
		)

		var panel := _panel(body)
		panel.add_child(button)


func _open_brochure(
	record: Dictionary,
	procedures: Array,
	heading: String
) -> void:
	var brochure := PopupPanel.new()
	brochure.name = "BrochurePopup"
	brochure.exclusive = true
	brochure.size = Vector2i(680, 780)

	add_child(brochure)

	brochure.popup_hide.connect(brochure.queue_free)

	var background := PanelContainer.new()
	background.set_anchors_and_offsets_preset(
		Control.PRESET_FULL_RECT
	)
	brochure.add_child(background)

	var panel_style := StyleBoxFlat.new()
	panel_style.bg_color = SURFACE
	panel_style.border_color = BORDER
	panel_style.set_border_width_all(1)
	panel_style.set_corner_radius_all(7)
	panel_style.set_content_margin_all(18)
	background.add_theme_stylebox_override(
		"panel", panel_style
	)

	var layout := VBoxContainer.new()
	layout.add_theme_constant_override(
		"separation", 10
	)
	background.add_child(layout)

	var header := HBoxContainer.new()
	layout.add_child(header)

	var heading_column := VBoxContainer.new()
	heading_column.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)
	header.add_child(heading_column)

	_add_label(heading_column, heading, 20, TEXT)

	_add_label(
		heading_column,
		str(record.get("name", "")),
		13,
		MUTED,
		true
	)

	var close_button := Button.new()
	close_button.text = "✕"
	close_button.custom_minimum_size = Vector2(36, 36)
	close_button.pressed.connect(brochure.hide)
	header.add_child(close_button)

	var scroll := ScrollContainer.new()
	scroll.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)
	scroll.size_flags_vertical = (
		Control.SIZE_EXPAND_FILL
	)
	scroll.horizontal_scroll_mode = (
		ScrollContainer.SCROLL_MODE_DISABLED
	)
	layout.add_child(scroll)

	var content := VBoxContainer.new()
	content.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)
	content.add_theme_constant_override(
		"separation", 14
	)
	scroll.add_child(content)

	for procedure in procedures:
		var explanation := _text(
			procedure.get("explanation")
		)

		if not explanation.is_empty():
			_add_label(
				content,
				explanation,
				12,
				MUTED,
				true
			)

		for step in procedure.get("steps", []):
			if not step is Dictionary:
				continue

			_add_brochure_step(content, step)

	brochure.popup_centered_clamped(
		Vector2i(680, 780),
		0.85
	)


func _add_brochure_step(
	parent: VBoxContainer,
	step: Dictionary
) -> void:
	var card := _panel(parent, DARK)

	var content := VBoxContainer.new()
	content.add_theme_constant_override(
		"separation", 8
	)
	card.add_child(content)

	var heading := (
		str(step.get("step_order", 0))
		+ ". "
		+ str(step.get("title", ""))
	)

	_add_label(content, heading, 15, TEXT, true)

	var step_id := str(step.get("step_id", ""))
	var media_id := str(STEP_MEDIA.get(step_id, ""))

	if not media_id.is_empty():
		var media: Dictionary = media_catalogue.get(
			media_id, {}
		)

		var file_path := str(
			media.get("file_path", "")
		)

		if not file_path.is_empty():
			var resource_path := file_path

			if not resource_path.begins_with("res://"):
				resource_path = (
                    "res://"
					+ resource_path.trim_prefix("/")
				)

			if ResourceLoader.exists(resource_path):
				var texture := load(resource_path)

				if texture is Texture2D:
					var image := TextureRect.new()
					image.texture = texture
					image.custom_minimum_size.y = 240
					image.expand_mode = (
						TextureRect.EXPAND_IGNORE_SIZE
					)
					image.stretch_mode = (
						TextureRect.STRETCH_KEEP_ASPECT_CENTERED
					)
					content.add_child(image)

	var explanation := _text(
		step.get("explanation")
	)

	if not explanation.is_empty():
		_add_label(
			content,
			explanation,
			12,
			MUTED,
			true
		)

# --------------------------------------------------
# UI helpers
# --------------------------------------------------

func _section(
	parent: Node,
	title: String
) -> VBoxContainer:
	var panel := _panel(parent)

	var content := VBoxContainer.new()
	content.add_theme_constant_override(
		"separation", 8
	)
	panel.add_child(content)

	_add_label(
		content,
		title,
		14
	)

	return content


func _collapsible(
	parent: Node,
	title: String
) -> VBoxContainer:
	var panel := _panel(parent)

	var content := VBoxContainer.new()
	content.add_theme_constant_override(
		"separation", 7
	)
	panel.add_child(content)

	var button := Button.new()
	button.text = title + "  ▸"
	button.alignment = (
		HORIZONTAL_ALIGNMENT_LEFT
	)
	button.custom_minimum_size.y = 32
	button.add_theme_font_size_override(
		"font_size", 12
	)
	content.add_child(button)

	var details := VBoxContainer.new()
	details.visible = false
	details.add_theme_constant_override(
		"separation", 6
	)
	content.add_child(details)

	button.pressed.connect(
		func() -> void:
			details.visible = not details.visible
			button.text = title + (
				"  ▾"
				if details.visible
				else "  ▸"
			)
	)

	return details


func _panel(
	parent: Node,
	color: Color = SURFACE
) -> PanelContainer:
	var panel := PanelContainer.new()
	panel.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)

	var style := StyleBoxFlat.new()
	style.bg_color = color
	style.border_color = BORDER
	style.set_border_width_all(1)
	style.set_corner_radius_all(7)

	style.content_margin_left = 10
	style.content_margin_right = 10
	style.content_margin_top = 8
	style.content_margin_bottom = 8

	panel.add_theme_stylebox_override(
		"panel", style
	)
	parent.add_child(panel)

	return panel


func _add_label(
	parent: Node,
	value: String,
	font_size: int = 13,
	color: Color = TEXT,
	wrap_text: bool = false
) -> Label:
	var label := Label.new()
	label.text = value

	label.add_theme_font_size_override(
		"font_size", font_size
	)
	label.add_theme_color_override(
		"font_color", color
	)

	label.autowrap_mode = (
		TextServer.AUTOWRAP_WORD_SMART
		if wrap_text
		else TextServer.AUTOWRAP_OFF
	)

	label.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
		if wrap_text
		else Control.SIZE_FILL
	)

	parent.add_child(label)
	return label


func _text(value: Variant) -> String:
	return (
		""
		if value == null
		else str(value).strip_edges()
	)


func _join_existing(values: Array) -> String:
	var parts := PackedStringArray()

	for value in values:
		var item := _text(value)

		if not item.is_empty():
			parts.append(item)

	return "\n\n".join(parts)


func _status(entry: Dictionary) -> String:
	if str(
		entry.get("code", "")
	).is_empty():
		return "Not rule-evaluated"

	return str(
		entry["outcome"].get(
			"status", "Unclassified"
		)
	)


func _status_color(entry: Dictionary) -> Color:
	match _status(entry):
		"Available":
			return AVAILABLE
		"Caution":
			return CAUTION
		"Excluded":
			return EXCLUDED

	return MUTED


func _style_action(
	button: Button,
	selected: bool
) -> void:
	var style := StyleBoxFlat.new()

	style.bg_color = (
		ACTIVE if selected else DARK
	)
	style.border_color = (
		Color("#5799FA")
		if selected
		else BORDER
	)
	style.set_border_width_all(1)
	style.set_corner_radius_all(7)

	style.content_margin_left = 8
	style.content_margin_right = 8
	style.content_margin_top = 7
	style.content_margin_bottom = 7

	button.add_theme_stylebox_override(
		"normal", style
	)

	var hover: StyleBoxFlat = style.duplicate()
	hover.bg_color = Color("#344F73")

	button.add_theme_stylebox_override(
		"hover", hover
	)

	button.add_theme_color_override(
		"font_color", TEXT
	)


func _clear_children(parent: Node) -> void:
	for child in parent.get_children():
		parent.remove_child(child)
		child.queue_free()


func _show_card_cautions(entry: Dictionary) -> void:
	var outcome: Dictionary = entry.get("outcome", {})
	var alerts: Array = outcome.get("soft_alerts", [])

	if alerts.is_empty():
		return

	var evaluation: Dictionary = _current_evaluation()
	var explanations: Dictionary = evaluation.get(
		"explanations", {}
	)
	var knowledge: Dictionary = evaluation.get(
		"knowledge", {}
	)
	var rule_details: Dictionary = knowledge.get(
		"rule_details", {}
	)

	var treatment_code: String = str(
		entry.get("code", "")
	)

	var messages := PackedStringArray()

	for alert_id in alerts:
		var rule_id: String = str(alert_id)
		var parts := PackedStringArray()

		# Find the explanation for the specific
		# clinical alert returned by the backend.
		for key in ["why", "why_not"]:
			for rule in explanations.get(key, []):
				if not rule is Dictionary:
					continue

				if str(rule.get("rule_id", "")) != rule_id:
					continue

				var treatment: Variant = rule.get(
					"treatment", {}
				)

				if treatment is Dictionary:
					var associated_code := str(
						treatment.get("code", "")
					)

					if (
						not associated_code.is_empty()
						and associated_code != treatment_code
					):
						continue

				var description: String = _text(
					rule.get("description")
				)

				if (
					not description.is_empty()
					and not parts.has(description)
				):
					parts.append(description)

		# Include the rule's available clinical
		# information from the knowledge layer.
		var detail: Variant = rule_details.get(
			rule_id, {}
		)

		if detail is Dictionary:
			for field in [
				"clinical_detail",
				"limitations"
			]:
				var information: String = _text(
					detail.get(field)
				)

				if (
					not information.is_empty()
					and not parts.has(information)
				):
					parts.append(information)

		if parts.is_empty():
			messages.append(
				"No explanation was returned for "
				+ "clinical alert " + rule_id + "."
			)
		else:
			messages.append("\n\n".join(parts))

	var record: Dictionary = entry.get("record", {})
	var treatment_name: String = str(
		record.get("name", "Treatment")
	)

	_show_popup(
		"Clinical caution: " + treatment_name,
		"\n\n".join(messages)
	)


func _show_popup(
	title: String,
	message: String
) -> void:
	popup.title = title
	popup.dialog_text = message

	popup.popup_centered_clamped(
		Vector2i(550, 330),
		0.85
	)
