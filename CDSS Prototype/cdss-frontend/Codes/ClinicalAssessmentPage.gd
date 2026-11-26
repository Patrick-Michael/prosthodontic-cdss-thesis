extends VBoxContainer

signal undo_requested()
signal redo_requested()
signal reset_requested()
signal span_selection_changed()


# --------------------------------------------------
# Existing scene references
# --------------------------------------------------

@onready var assessment_scroll: ScrollContainer = (
	$AssessmentScroll
)

@onready var assessment_content: VBoxContainer = (
	$AssessmentScroll/AssessmentContent
)

@onready var case_content: Control = (
	$AssessmentScroll/AssessmentContent/
	CaseHeader/Content/CaseContent
)

@onready var case_toggle: Button = (
	$AssessmentScroll/AssessmentContent/
	CaseHeader/Content/ToggleCaseHeader
)

@onready var select_all: CheckBox = (
	$AssessmentScroll/AssessmentContent/
	MissingSpans/Content/SelectAllSpans
)

@onready var span_list: VBoxContainer = (
	$AssessmentScroll/AssessmentContent/
	MissingSpans/Content/SpanList
)

@onready var selection_count: Label = (
	$AssessmentScroll/AssessmentContent/
	MissingSpans/Content/SelectionCount
)

@onready var spans_note: Label = (
	$AssessmentScroll/AssessmentContent/
	MissingSpans/Content/SpansNote
)

@onready var unsupported_note: Label = (
	$AssessmentScroll/AssessmentContent/
	MissingSpans/Content/UnsupportedNote
)

@onready var explanation_popup: AcceptDialog = (
	$ExplanationPopup
)


# --------------------------------------------------
# Visual constants
# --------------------------------------------------

const UI_TEXT := Color("#E5EDF7")
const UI_MUTED := Color("#AEBFD1")
const UI_BLUE := Color("#2868C9")
const UI_BORDER := Color("#405168")
const UI_PANEL := Color("#233246")

const FONT_HEADING := 15
const FONT_BODY := 12
const FONT_SECONDARY := 11

const CONTROL_HEIGHT := 34.0
const SMALL_CONTROL_HEIGHT := 28.0


# --------------------------------------------------
# Clinical state
# --------------------------------------------------

var spans_loaded: bool = false
var span_controls: Array[CheckBox] = []
var terminology: Dictionary = {}

# --------------------------------------------------
# Primary action styling state
# --------------------------------------------------

var primary_action_style: StyleBoxFlat
var primary_hover_style: StyleBoxFlat
var primary_pressed_style: StyleBoxFlat

var original_encounter_minimum_size: Vector2
var original_evaluate_minimum_size: Vector2

var primary_action_initialized: bool = false


# --------------------------------------------------
# Initialization
# --------------------------------------------------

func _ready() -> void:
	_configure_layout()
	_configure_compact_typography()

	case_toggle.pressed.connect(
		_toggle_case_header
	)

	select_all.toggled.connect(
		_select_all_spans
	)

	var info_button: Button = (
		$AssessmentScroll/AssessmentContent/
		Measurements/Content/HbA1cRow/HbA1cInfo
	)

	info_button.pressed.connect(
		_show_hba1c_information
	)

	var actions: Node = (
		$AssessmentScroll/AssessmentContent/
		CaseActions/Content
	)

	actions.get_node(
		"HistoryButtons/UndoButton"
	).pressed.connect(
		func(): undo_requested.emit()
	)

	actions.get_node(
		"HistoryButtons/RedoButton"
	).pressed.connect(
		func(): redo_requested.emit()
	)

	actions.get_node(
		"HistoryButtons/ResetButton"
	).pressed.connect(
		func(): reset_requested.emit()
	)

	select_all.disabled = true

	selection_count.text = (
		"No clinical case loaded."
	)

	spans_note.text = (
		"Select a patient encounter to load "
		+ "missing-tooth spans."
	)

	unsupported_note.text = ""

	set_history_actions(false, false)

	_configure_section_guidance()


# --------------------------------------------------
# Compact layout
# --------------------------------------------------

func _configure_layout() -> void:
	assessment_scroll.horizontal_scroll_mode = (
		ScrollContainer.SCROLL_MODE_DISABLED
	)

	assessment_scroll.vertical_scroll_mode = (
		ScrollContainer.SCROLL_MODE_AUTO
	)

	assessment_scroll.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)

	assessment_scroll.size_flags_vertical = (
		Control.SIZE_EXPAND_FILL
	)

	assessment_content.custom_minimum_size.x = 320.0

	assessment_content.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)

	assessment_content.add_theme_constant_override(
		"separation", 11
	)

	var measurement_row: HBoxContainer = (
		$AssessmentScroll/AssessmentContent/
		Measurements/Content/HbA1cRow
	)

	var hba1c_label: Label = (
		measurement_row.get_node("HbA1cLabel")
	)

	var hba1c_info: Button = (
		measurement_row.get_node("HbA1cInfo")
	)

	var hba1c_value: SpinBox = (
		measurement_row.get_node("HbA1cValue")
	)

	measurement_row.add_theme_constant_override(
		"separation", 6
	)

	hba1c_label.autowrap_mode = (
		TextServer.AUTOWRAP_OFF
	)

	hba1c_label.custom_minimum_size.x = 0.0

	hba1c_label.size_flags_horizontal = (
		Control.SIZE_SHRINK_BEGIN
	)

	hba1c_label.add_theme_font_size_override(
		"font_size", FONT_BODY
	)

	hba1c_info.text = "i"

	hba1c_info.custom_minimum_size = (
		Vector2(26, 26)
	)

	hba1c_info.size_flags_horizontal = (
		Control.SIZE_SHRINK_BEGIN
	)

	hba1c_info.add_theme_font_size_override(
		"font_size", FONT_SECONDARY
	)

	hba1c_info.tooltip_text = "What is HbA1c?"

	hba1c_value.custom_minimum_size.x = 90.0

	hba1c_value.custom_minimum_size.y = (
		CONTROL_HEIGHT
	)

	hba1c_value.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)

	select_all.autowrap_mode = (
		TextServer.AUTOWRAP_OFF
	)


# --------------------------------------------------
# Shared compact typography and spacing
# --------------------------------------------------

func _configure_compact_typography() -> void:
	# Apply compact text sizes without removing
	# any existing clinical fields or controls.
	_style_descendants(assessment_content)

	# Section panels retain clear visual boundaries.
	for section_name in [
		"CaseHeader",
		"Measurements",
		"MissingSpans",
		"CaseActions"
	]:
		var section := assessment_content.get_node_or_null(
			section_name
		)

		if section is PanelContainer:
			_style_section_panel(section)

			var content_node := section.get_node_or_null(
				"Content"
			)

			if content_node is VBoxContainer:
				content_node.add_theme_constant_override(
					"separation", 9
				)

	# Keep encounter selection prominent
	# without using excessively large buttons.
	var encounter_button := case_content.get_node_or_null(
		"SelectEncounter"
	)

	if encounter_button is Button:
		encounter_button.custom_minimum_size.y = (
			CONTROL_HEIGHT
		)

		encounter_button.add_theme_font_size_override(
			"font_size", FONT_BODY
		)

	var evaluate_button := get_node_or_null(
		"AssessmentScroll/AssessmentContent/"
		+ "CaseActions/Content/EvaluateButton"
	)

	if evaluate_button is Button:
		evaluate_button.custom_minimum_size.y = (
			CONTROL_HEIGHT
		)

		evaluate_button.add_theme_font_size_override(
			"font_size", FONT_BODY
		)

	# History controls are secondary actions.
	var history := get_node_or_null(
		"AssessmentScroll/AssessmentContent/"
		+ "CaseActions/Content/HistoryButtons"
	)

	if history is Control:
		for child in history.get_children():
			if child is Button:
				child.custom_minimum_size.y = (
					SMALL_CONTROL_HEIGHT
				)

				child.add_theme_font_size_override(
					"font_size", FONT_SECONDARY
				)


func _style_descendants(root: Node) -> void:
	for child in root.get_children():
		if child is Label:
			child.add_theme_font_size_override(
				"font_size", FONT_BODY
			)

		elif child is Button:
			child.add_theme_font_size_override(
				"font_size", FONT_BODY
			)

		elif child is CheckBox:
			child.add_theme_font_size_override(
				"font_size", FONT_BODY
			)

		elif child is SpinBox:
			child.add_theme_font_size_override(
				"font_size", FONT_BODY
			)

		elif child is OptionButton:
			child.add_theme_font_size_override(
				"font_size", FONT_BODY
			)

		# Existing node hierarchy and signals
		# are deliberately left unchanged.
		_style_descendants(child)


func _style_section_panel(
	panel: PanelContainer
) -> void:
	var base_style: StyleBox = (
		panel.get_theme_stylebox("panel")
	)

	var style: StyleBoxFlat

	if base_style is StyleBoxFlat:
		style = (
			base_style.duplicate() as StyleBoxFlat
		)
	else:
		style = StyleBoxFlat.new()
		style.bg_color = UI_PANEL

	style.border_color = UI_BORDER
	style.set_border_width_all(1)
	style.set_corner_radius_all(7)

	style.content_margin_left = 10
	style.content_margin_right = 10
	style.content_margin_top = 9
	style.content_margin_bottom = 9

	panel.add_theme_stylebox_override(
		"panel", style
	)


# --------------------------------------------------
# Patient and encounter header
# --------------------------------------------------

func _toggle_case_header() -> void:
	case_content.visible = not case_content.visible

	if case_content.visible:
		case_toggle.text = (
			"Patient and encounter  ▾"
		)
	else:
		case_toggle.text = (
			"Patient and encounter  ▸"
		)


# --------------------------------------------------
# Backend-driven missing-span presentation
# --------------------------------------------------

func clear_case_spans() -> void:
	spans_loaded = false

	for checkbox in span_controls:
		span_list.remove_child(checkbox)
		checkbox.queue_free()

	span_controls.clear()

	select_all.set_pressed_no_signal(false)
	select_all.disabled = true

	selection_count.text = (
		"No clinical case loaded."
	)

	spans_note.text = (
		"Select a patient encounter to load "
		+ "missing-tooth spans."
	)

	unsupported_note.text = ""

	span_selection_changed.emit()


func set_case_spans(
	selectable_spans: Array,
	missing_spans: Array,
	tooth_controller: Node3D
) -> void:
	var old_selection: Array = get_selected_spans()

	for checkbox in span_controls:
		span_list.remove_child(checkbox)
		checkbox.queue_free()

	span_controls.clear()
	spans_loaded = true

	for span_value in selectable_spans:
		if not span_value is Array:
			continue

		var span: Array = span_value
		var identifiers: PackedStringArray = []
		var names: PackedStringArray = []

		for tooth in span:
			var fdi: String = str(tooth)

			identifiers.append(fdi)

			names.append(
				str(
					tooth_controller.get_tooth_name(fdi)
				).capitalize()
			)

		var checkbox := CheckBox.new()
		var span_style := StyleBoxFlat.new()
		span_style.bg_color = Color("#161D27")
		span_style.border_color = Color("#405168")
		span_style.set_border_width_all(1)
		span_style.set_corner_radius_all(7)
		span_style.content_margin_left = 12
		span_style.content_margin_right = 12
		span_style.content_margin_top = 8
		span_style.content_margin_bottom = 8

		var hover_style := span_style.duplicate()
		hover_style.bg_color = Color("#344F73")
		hover_style.border_color = Color("#5799FA")

		checkbox.add_theme_stylebox_override(
			"hover", hover_style
		)
		checkbox.add_theme_stylebox_override(
			"normal", span_style
		)

		var selected_style := span_style.duplicate()
		selected_style.bg_color = Color("#294D79")
		selected_style.border_color = Color("#5799FA")

		checkbox.add_theme_stylebox_override(
			"pressed", selected_style
		)

		checkbox.add_theme_stylebox_override(
   		 "hover_pressed", selected_style
		)

		checkbox.text = (
			", ".join(names)
			+ " (FDI "
			+ ", ".join(identifiers)
			+ ")"
		)

		checkbox.autowrap_mode = (
			TextServer.AUTOWRAP_WORD_SMART
		)

		checkbox.add_theme_font_size_override(
			"font_size", FONT_BODY
		)

		checkbox.custom_minimum_size.y = 28

		checkbox.set_meta(
			"clinical_span",
			span.duplicate(true)
		)

		checkbox.set_pressed_no_signal(
			span in old_selection
		)

		checkbox.toggled.connect(
			_on_span_selection_changed
		)

		span_list.add_child(checkbox)
		span_controls.append(checkbox)

	select_all.disabled = span_controls.is_empty()

	spans_note.text = (
		"Select missing-tooth spans for evaluation."
	)

	var unavailable: Array = []

	for missing in missing_spans:
		if not missing is Array:
			continue

		for tooth in missing:
			var fdi: String = str(tooth)
			var selectable: bool = false

			for candidate in selectable_spans:
				if candidate is Array and fdi in candidate:
					selectable = true
					break

			if not selectable:
				unavailable.append(fdi)

	if unavailable.is_empty():
		unsupported_note.text = ""
	else:
		var unavailable_names: PackedStringArray = []

		for fdi in unavailable:
			unavailable_names.append(
				str(
					tooth_controller.get_tooth_name(fdi)
				).capitalize()
				+ " (FDI " + fdi + ")"
			)

		unsupported_note.text = (
			"Not selectable under the current "
			+ "backend span-selection rules: "
			+ ", ".join(unavailable_names)
		)

	_update_selection_summary()


func get_selected_spans() -> Array:
	var selected: Array = []

	for checkbox in span_controls:
		if checkbox.button_pressed:
			selected.append(
				checkbox.get_meta(
					"clinical_span"
				).duplicate(true)
			)

	return selected


func _select_all_spans(checked: bool) -> void:
	for checkbox in span_controls:
		checkbox.set_pressed_no_signal(checked)

	_update_selection_summary()


func _on_span_selection_changed(
	_checked: bool
) -> void:
	_update_selection_summary()


func _update_selection_summary() -> void:
	var selected: int = get_selected_spans().size()
	var total: int = span_controls.size()

	selection_count.text = (
		str(selected)
		+ " of "
		+ str(total)
		+ " spans selected"
	)

	select_all.set_pressed_no_signal(
		total > 0 and selected == total
	)

	span_selection_changed.emit()
	
	
# --------------------------------------------------
# Clinical history controls
# --------------------------------------------------

func set_history_actions(
	can_undo: bool,
	can_redo: bool
) -> void:
	var buttons: Node = (
		$AssessmentScroll/AssessmentContent/
		CaseActions/Content/HistoryButtons
	)

	buttons.get_node("UndoButton").disabled = (
		not can_undo
	)

	buttons.get_node("RedoButton").disabled = (
		not can_redo
	)


# --------------------------------------------------
# Odontogram missing-tooth preview
# --------------------------------------------------

func display_local_missing_teeth(
	missing: Array[String],
	tooth_names: Dictionary
) -> void:
	if spans_loaded:
		return

	if missing.is_empty():
		spans_note.text = (
			"No missing teeth displayed."
		)
		return

	var names: PackedStringArray = []

	for fdi in missing:
		names.append(
			str(tooth_names.get(fdi, "Tooth"))
			+ " (FDI " + fdi + ")"
		)

	spans_note.text = (
		"Odontogram preview: "
		+ ", ".join(names)
	)


# --------------------------------------------------
# Clinical Assessment workflow hierarchy
# --------------------------------------------------

func _configure_section_guidance() -> void:
	var case_section: VBoxContainer = (
		$AssessmentScroll/AssessmentContent/
		CaseHeader/Content
	)

	var measurements_section: VBoxContainer = (
		$AssessmentScroll/AssessmentContent/
		Measurements/Content
	)

	var spans_section: VBoxContainer = (
		$AssessmentScroll/AssessmentContent/
		MissingSpans/Content
	)

	var actions_section: VBoxContainer = (
		$AssessmentScroll/AssessmentContent/
		CaseActions/Content
	)

	# Replace redundant scene headings with
	# consistent workflow headings.
	measurements_section.get_node("Heading").hide()
	spans_section.get_node("Heading").hide()

	_add_section_guidance(
		case_section,
		"1. Choose clinical encounter",
		"Select a visit to load its recorded findings.",
		"An encounter is a recorded patient visit. "
		+ "Choose one to load its information into the "
		+ "CDSS working case. The original patient "
		+ "record is not modified."
	)

	_add_section_guidance(
		measurements_section,
		"2. Review recorded measurements",
		"Review the measurements used in the assessment.",
		"This section displays clinical measurements "
		+ "retrieved for the working case, such as HbA1c. "
		+ "Values can be adjusted to explore scenarios "
		+ "without modifying the original patient record."
	)

	_add_section_guidance(
		spans_section,
		"3. Select missing-tooth spans",
		"Choose the missing teeth or spaces to evaluate.",
		"A span is a missing-tooth position or group "
		+ "of adjacent missing teeth. Select the spans "
		+ "to evaluate with the current working case."
	)

	_add_section_guidance(
		actions_section,
		"4. Evaluate treatment options",
		"Evaluate the selected spans using the working case.",
		"The CDSS evaluates the selected spans using "
		+ "the current clinical information and presents "
		+ "treatment alternatives with explanations. "
		+ "The practitioner and patient retain responsibility "
		+ "for the final treatment decision."
	)


func _add_section_guidance(
	section: VBoxContainer,
	heading_text: String,
	description_text: String,
	help_text: String
) -> void:
	var heading_row := HBoxContainer.new()
	heading_row.name = "WorkflowHeading"

	heading_row.add_theme_constant_override(
		"separation", 6
	)

	var heading := Label.new()
	heading.name = "WorkflowTitle"
	heading.text = heading_text

	heading.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)

	heading.autowrap_mode = (
		TextServer.AUTOWRAP_WORD_SMART
	)

	heading.add_theme_font_size_override(
		"font_size", FONT_HEADING
	)

	heading.add_theme_color_override(
		"font_color", UI_TEXT
	)

	var help_button := Button.new()
	help_button.name = "SectionHelp"
	help_button.text = "?"
	help_button.tooltip_text = (
		"Help: " + heading_text
	)

	help_button.custom_minimum_size = (
		Vector2(26, 26)
	)

	help_button.add_theme_font_size_override(
		"font_size", FONT_SECONDARY
	)

	help_button.focus_mode = Control.FOCUS_ALL

	help_button.pressed.connect(
		func() -> void:
			show_explanation(help_text)
	)

	heading_row.add_child(heading)
	heading_row.add_child(help_button)

	var description := Label.new()
	description.name = "WorkflowDescription"
	description.text = description_text

	description.autowrap_mode = (
		TextServer.AUTOWRAP_WORD_SMART
	)

	description.add_theme_font_size_override(
		"font_size", FONT_SECONDARY
	)

	description.add_theme_color_override(
		"font_color", UI_MUTED
	)

	section.add_child(heading_row)
	section.move_child(heading_row, 0)

	section.add_child(description)
	section.move_child(description, 1)


# --------------------------------------------------
# Workflow-dependent primary action styling
# --------------------------------------------------

func _initialize_primary_action_styles() -> void:
	if primary_action_initialized:
		return

	var encounter_button: Button = (
		case_content.get_node("SelectEncounter")
	)

	var evaluate_button: Button = (
		$AssessmentScroll/AssessmentContent/
		CaseActions/Content/EvaluateButton
	)

	original_encounter_minimum_size = (
		encounter_button.custom_minimum_size
	)

	original_evaluate_minimum_size = (
		evaluate_button.custom_minimum_size
	)

	primary_action_style = _make_primary_style(
		UI_BLUE
	)

	primary_hover_style = _make_primary_style(
		Color("#367CE5")
	)

	primary_pressed_style = _make_primary_style(
		Color("#2058AD")
	)

	primary_action_initialized = true


func _make_primary_style(
	background_color: Color
) -> StyleBoxFlat:
	var style := StyleBoxFlat.new()

	style.bg_color = background_color
	style.border_color = Color("#5799FA")

	style.set_border_width_all(1)
	style.set_corner_radius_all(7)

	style.content_margin_left = 12
	style.content_margin_right = 12
	style.content_margin_top = 7
	style.content_margin_bottom = 7

	return style


func _set_button_primary(
	button: Button,
	is_primary: bool,
	normal_minimum_size: Vector2
) -> void:
	if is_primary:
		button.add_theme_stylebox_override(
			"normal",
			primary_action_style
		)

		button.add_theme_stylebox_override(
			"hover",
			primary_hover_style
		)

		button.add_theme_stylebox_override(
			"pressed",
			primary_pressed_style
		)

		button.add_theme_color_override(
			"font_color",
			Color.WHITE
		)

		button.add_theme_color_override(
			"font_hover_color",
			Color.WHITE
		)

		button.add_theme_color_override(
			"font_pressed_color",
			Color.WHITE
		)

		button.custom_minimum_size = Vector2(
			normal_minimum_size.x,
			maxf(
				normal_minimum_size.y,
				CONTROL_HEIGHT
			)
		)

	else:
		button.remove_theme_stylebox_override(
			"normal"
		)

		button.remove_theme_stylebox_override(
			"hover"
		)

		button.remove_theme_stylebox_override(
			"pressed"
		)

		button.remove_theme_color_override(
			"font_color"
		)

		button.remove_theme_color_override(
			"font_hover_color"
		)

		button.remove_theme_color_override(
			"font_pressed_color"
		)

		button.custom_minimum_size = Vector2(
			normal_minimum_size.x,
			maxf(
				normal_minimum_size.y,
				SMALL_CONTROL_HEIGHT
			)
		)


func set_workflow_emphasis(
	case_loaded: bool,
	can_choose_encounter: bool,
	has_selected_spans: bool,
	can_evaluate: bool,
	is_busy: bool
) -> void:
	_initialize_primary_action_styles()

	var encounter_button: Button = (
		case_content.get_node("SelectEncounter")
	)

	var evaluate_button: Button = (
		$AssessmentScroll/AssessmentContent/
		CaseActions/Content/EvaluateButton
	)

	var spans_panel: PanelContainer = (
		$AssessmentScroll/AssessmentContent/
		MissingSpans
	)

	var emphasize_encounter: bool = (
		not case_loaded
		and can_choose_encounter
		and not is_busy
	)

	var emphasize_spans: bool = (
		case_loaded
		and not has_selected_spans
		and not is_busy
	)

	var emphasize_evaluation: bool = (
		case_loaded
		and has_selected_spans
		and can_evaluate
		and not is_busy
	)

	_set_button_primary(
		encounter_button,
		emphasize_encounter,
		original_encounter_minimum_size
	)

	_set_button_primary(
		evaluate_button,
		emphasize_evaluation,
		original_evaluate_minimum_size
	)

	# Restore compact panel styling before
	# applying workflow emphasis.
	_style_section_panel(spans_panel)

	if emphasize_spans:
		var base_style: StyleBox = (
			spans_panel.get_theme_stylebox("panel")
		)

		var highlighted_style: StyleBoxFlat

		if base_style is StyleBoxFlat:
			highlighted_style = (
				base_style.duplicate() as StyleBoxFlat
			)
		else:
			highlighted_style = StyleBoxFlat.new()
			highlighted_style.bg_color = UI_PANEL

		highlighted_style.border_color = (
			Color("#5799FA")
		)

		highlighted_style.set_border_width_all(2)
		highlighted_style.set_corner_radius_all(7)

		spans_panel.add_theme_stylebox_override(
			"panel",
			highlighted_style
		)

	encounter_button.text = (
		"Change encounter"
		if case_loaded
		else "Choose encounter"
	)


# --------------------------------------------------
# Contextual explanations
# --------------------------------------------------

func _show_hba1c_information() -> void:
	var entry: Dictionary = terminology.get(
		"LOINC|4548-4", {}
	)

	var explanation_text: String = str(
		entry.get("explanation", "")
	)

	if explanation_text.is_empty():
		show_explanation(
			"HbA1c information is currently unavailable."
		)
		return

	show_explanation(explanation_text)

	


func show_explanation(
	explanation_text: String
) -> void:
	explanation_popup.dialog_autowrap = true

	var text_label: Label = (
		explanation_popup.get_label()
	)

	text_label.custom_minimum_size.x = 0.0
	text_label.custom_maximum_size.x = 340.0

	text_label.autowrap_mode = (
		TextServer.AUTOWRAP_WORD_SMART
	)

	text_label.add_theme_font_size_override(
		"font_size", FONT_BODY
	)

	explanation_popup.dialog_text = explanation_text

	explanation_popup.popup_centered_clamped(
		Vector2i(380, 180),
		0.75
	)
