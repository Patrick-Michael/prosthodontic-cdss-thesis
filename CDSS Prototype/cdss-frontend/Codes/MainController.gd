extends Control

# --------------------------------------------------
# Scene references
# --------------------------------------------------

@onready var odontogram = (
	$AppLayout/MainLayout/VisualizationPanel/
	ViewportContainer/DentalViewport/DentalWorld/Odontogram3D
)

@onready var tooth_controller = (
	$AppLayout/MainLayout/VisualizationPanel/
	ViewportContainer/DentalViewport/DentalWorld/
	Odontogram3D/ToothInteractionController
)

@onready var assessment_page = get_node(
	"AppLayout/MainLayout/InformationPanel/"
	+ "InformationMargin/InformationContent/"
	+ "PageContainer/ClinicalAssessmentPage"
)

@onready var dental_camera: Camera3D = (
	$AppLayout/MainLayout/VisualizationPanel/
	ViewportContainer/DentalViewport/DentalWorld/DentalCamera
)

@onready var viewport_container: SubViewportContainer = (
	$AppLayout/MainLayout/VisualizationPanel/ViewportContainer
)

@onready var dental_viewport: SubViewport = (
	$AppLayout/MainLayout/VisualizationPanel/
	ViewportContainer/DentalViewport
)

@onready var visualization_overlay: Control = (
	$AppLayout/MainLayout/VisualizationPanel/
	VisualizationOverlay
)

@onready var bottom_toolbar: Control = (
	$AppLayout/MainLayout/VisualizationPanel/
	VisualizationOverlay/BottomToolbar
)

@onready var rotation_gizmo: Control = (
	$AppLayout/MainLayout/VisualizationPanel/RotationGizmo
)

@onready var visualization_panel: PanelContainer = (
	$AppLayout/MainLayout/VisualizationPanel
)

@onready var information_panel: PanelContainer = (
	$AppLayout/MainLayout/InformationPanel
)

@onready var navigation_bar: Control = (
	$AppLayout/NavigationBar
)

@onready var main_layout: HSplitContainer = (
	$AppLayout/MainLayout
)

@onready var treatment_options_bar: Control = (
	$AppLayout/TreatmentOptionsBar
)

@onready var fullscreen_button: Button = (
	$AppLayout/MainLayout/VisualizationPanel/
	VisualizationOverlay/FullscreenVisualizationButton
)

@onready var controls_help_button: Button = (
	$AppLayout/MainLayout/VisualizationPanel/
	ControlsHelpButton
)

@onready var controls_popup: PanelContainer = (
	$AppLayout/MainLayout/VisualizationPanel/
	ControlsPopup
)

@onready var page_heading: Label = (
	$AppLayout/MainLayout/InformationPanel/
	InformationMargin/InformationContent/PageHeading
)

@onready var page_container: Control = (
	$AppLayout/MainLayout/InformationPanel/
	InformationMargin/InformationContent/PageContainer
)

@onready var treatment_page: VBoxContainer = (
	$AppLayout/MainLayout/InformationPanel/
	InformationMargin/InformationContent/
	PageContainer/TreatmentComparisonPage
)

@onready var treatment_tab: Button = (
	$AppLayout/NavigationBar/TreatmentComparisonButton
)

@onready var clinical_tab: Button = (
	$AppLayout/NavigationBar/ClinicalAssessmentButton
)

@onready var patient_tab: Button = (
	$AppLayout/NavigationBar/PatientInformationButton
)


# --------------------------------------------------
# Evaluation and navigation state
# --------------------------------------------------

var treatment_results_ready: bool = false
var active_page_name: String = "ClinicalAssessmentPage"

var patient_name_label: Label

# Comparison overlay state.
# The overlay replaces the previous bottom workspace.
var comparison_open: bool = false

var comparison_panel: PanelContainer
var comparison_content: VBoxContainer
var comparison_close_button: Button

# Header background, independent of HBoxContainer styling.
var navigation_background: ColorRect

# Clinical assessment and treatment pages share
# the normal two-panel workspace.
var previous_main_visibility: bool = true


# --------------------------------------------------
# Backend clinical action signals
# --------------------------------------------------

signal clinical_tooth_edit_requested(
	fdi: String,
	present: bool
)

signal clinical_undo_requested()
signal clinical_redo_requested()
signal clinical_reset_requested()


# --------------------------------------------------
# Right-click contextual tooth editor
# --------------------------------------------------

@onready var tooth_editor_panel: PanelContainer = (
	$AppLayout/MainLayout/VisualizationPanel/
	VisualizationOverlay/ToothEditorPanel
)

@onready var tooth_popup_title: Label = (
	tooth_editor_panel.get_node(
		"MarginContainer/VBoxContainer/ToothTitle"
	)
)

@onready var tooth_popup_description: Label = (
	tooth_editor_panel.get_node(
		"MarginContainer/VBoxContainer/ToothDescription"
	)
)

@onready var tooth_popup_status: OptionButton = (
	tooth_editor_panel.get_node(
		"MarginContainer/VBoxContainer/ToothStatusPopup"
	)
)

@onready var tooth_popup_close: Button = (
	tooth_editor_panel.get_node(
		"MarginContainer/VBoxContainer/CloseToothPopup"
	)
)


# --------------------------------------------------
# Interaction configuration and state
# --------------------------------------------------

@export var pan_sensitivity: float = 0.08

const POPUP_MARGIN: float = 12.0
const POPUP_POINTER_OFFSET: float = 18.0

var panning: bool = false
var visualization_expanded: bool = false

var previous_navigation_visibility: bool = true
var previous_information_visibility: bool = true
var previous_treatment_bar_visibility: bool = false
var previous_split_offset: int = 0

# Clinical history remains managed by Python.
var backend_can_undo: bool = false
var backend_can_redo: bool = false
var backend_can_reset: bool = false


# --------------------------------------------------
# Initialization
# --------------------------------------------------

func _ready() -> void:
	fullscreen_button.pressed.connect(
		_toggle_visualization_fullscreen
	)

	tooth_controller.tooth_selected.connect(
		_on_tooth_selected
	)

	tooth_controller.tooth_popup_requested.connect(
		_on_tooth_right_clicked
	)

	assessment_page.undo_requested.connect(
		_undo_tooth_edit
	)

	assessment_page.redo_requested.connect(
		_redo_tooth_edit
	)

	assessment_page.reset_requested.connect(
		_reset_tooth_edits
	)

	tooth_popup_status.item_selected.connect(
		_on_popup_status_selected
	)

	tooth_popup_close.pressed.connect(
		_close_tooth_popup
	)

	tooth_editor_panel.mouse_filter = (
		Control.MOUSE_FILTER_STOP
	)

	tooth_editor_panel.hide()

	_refresh_missing_preview()
	_refresh_history_buttons()

	# Configure normal page navigation.
	_setup_page_navigation()

	# Create the shared dark header.
	_setup_navigation_header()

	# The new overlay replaces the lower comparison panel.
	_setup_comparison_overlay()

	treatment_page.comparison_mode_changed.connect(
		_on_comparison_mode_changed
	)

	clinical_tab.toggle_mode = false
	treatment_tab.toggle_mode = false
	patient_tab.toggle_mode = false

	treatment_results_ready = false
	treatment_tab.disabled = true

	var connector: Node = $CDSSConnection

	connector.media_loaded.connect(
		treatment_page.set_media_catalogue
	)
	
	connector.evaluation_completed.connect(
		_on_evaluation_completed
	)

	connector.case_loaded.connect(
		_on_clinical_case_loaded
	)

	_show_cdss_page(
		"ClinicalAssessmentPage",
		"Clinical Assessment"
	)


# --------------------------------------------------
# Tooth selection
# --------------------------------------------------

func _on_tooth_selected(_fdi: String) -> void:
	_close_tooth_popup()


func _on_tooth_right_clicked(
	_fdi: String,
	viewport_position: Vector2
) -> void:
	var visual_rect: Rect2 = (
		viewport_container.get_global_rect()
	)

	var viewport_size: Vector2 = (
		Vector2(dental_viewport.size)
	)

	var scale_factor := Vector2.ONE

	if viewport_size.x > 0.0 and viewport_size.y > 0.0:
		scale_factor = (
			visual_rect.size / viewport_size
		)

	var global_pointer: Vector2 = (
		visual_rect.position
		+ viewport_position * scale_factor
	)

	_open_tooth_popup_at(global_pointer)


# --------------------------------------------------
# Backend-controlled tooth editing
# --------------------------------------------------

func _change_tooth_status(
	fdi: String,
	present: bool
) -> void:
	if not tooth_controller.teeth.has(fdi):
		return

	if tooth_controller.is_tooth_present(fdi) == present:
		return

	clinical_tooth_edit_requested.emit(
		fdi,
		present
	)


func _on_popup_status_selected(index: int) -> void:
	var fdi: String = tooth_controller.selected_fdi

	if fdi.is_empty():
		return

	_change_tooth_status(
		fdi,
		index == 0
	)


# --------------------------------------------------
# Refresh contextual popup and missing-tooth preview
# --------------------------------------------------

func _refresh_tooth_interface(fdi: String) -> void:
	if not tooth_controller.teeth.has(fdi):
		return

	tooth_popup_title.text = (
		"Tooth " + fdi
	)

	tooth_popup_description.text = (
		tooth_controller.get_tooth_name(fdi).capitalize()
	)

	tooth_popup_status.select(
		0
		if tooth_controller.is_tooth_present(fdi)
		else 1
	)

	_refresh_missing_preview()
	_refresh_history_buttons()


func _refresh_missing_preview() -> void:
	var missing: Array[String] = (
		tooth_controller.get_missing_teeth()
	)

	var names: Dictionary = {}

	for fdi: String in missing:
		names[fdi] = (
			tooth_controller.get_tooth_name(fdi)
		)

	assessment_page.display_local_missing_teeth(
		missing,
		names
	)


# --------------------------------------------------
# Backend-controlled history availability
# --------------------------------------------------

func _refresh_history_buttons() -> void:
	assessment_page.set_history_actions(
		backend_can_undo,
		backend_can_redo
	)

	var reset_button: Button = (
		assessment_page.get_node(
			"AssessmentScroll/AssessmentContent/"
			+ "CaseActions/Content/HistoryButtons/"
			+ "ResetButton"
		)
	)

	reset_button.disabled = not backend_can_reset


func set_backend_history_actions(
	can_undo: bool,
	can_redo: bool,
	can_reset: bool
) -> void:
	backend_can_undo = can_undo
	backend_can_redo = can_redo
	backend_can_reset = can_reset

	_refresh_history_buttons()


# --------------------------------------------------
# Undo, Redo and Reset requests
# --------------------------------------------------

func _undo_tooth_edit() -> void:
	clinical_undo_requested.emit()


func _redo_tooth_edit() -> void:
	clinical_redo_requested.emit()


func _reset_tooth_edits() -> void:
	clinical_reset_requested.emit()


func _refresh_after_history() -> void:
	var fdi: String = tooth_controller.selected_fdi

	if not fdi.is_empty():
		_refresh_tooth_interface(fdi)
	else:
		_refresh_missing_preview()
		_refresh_history_buttons()


# --------------------------------------------------
# Synchronize the visual odontogram from Python
# --------------------------------------------------

func initialize_tooth_case(
	case_states: Dictionary
) -> void:
	var normalized_states: Dictionary = (
		tooth_controller.get_tooth_states()
	)

	for fdi: String in case_states:
		if normalized_states.has(fdi):
			normalized_states[fdi] = (
				bool(case_states[fdi])
			)

	tooth_controller.restore_tooth_states(
		normalized_states
	)

	# No local clinical history is created here.
	tooth_controller.clear_selection()

	_close_tooth_popup()

	_refresh_missing_preview()
	_refresh_history_buttons()


# --------------------------------------------------
# Contextual right-click popup
# --------------------------------------------------

func _open_tooth_popup_at(
	global_pointer: Vector2
) -> void:
	var fdi: String = tooth_controller.selected_fdi

	if fdi.is_empty():
		return

	_refresh_tooth_interface(fdi)

	tooth_editor_panel.show()
	tooth_editor_panel.reset_size()

	var overlay_rect: Rect2 = (
		visualization_overlay.get_global_rect()
	)

	var popup_size: Vector2 = (
		tooth_editor_panel.size
	)

	var viewport_rect: Rect2 = (
		viewport_container.get_global_rect()
	)

	var gizmo_rect: Rect2 = (
		rotation_gizmo.get_global_rect()
	)

	var left_bound: float = (
		viewport_rect.position.x
		+ POPUP_MARGIN
	)

	var right_bound: float = (
		viewport_rect.end.x
		- POPUP_MARGIN
	)

	if (
		rotation_gizmo.visible
		and gizmo_rect.intersects(viewport_rect)
	):
		right_bound = minf(
			right_bound,
			gizmo_rect.position.x - POPUP_MARGIN
		)

	var top_bound: float = (
		viewport_rect.position.y
		+ POPUP_MARGIN
	)

	var bottom_bound: float = (
		viewport_rect.end.y
		- POPUP_MARGIN
	)

	var x: float = (
		global_pointer.x + POPUP_POINTER_OFFSET
	)

	var y: float = (
		global_pointer.y + POPUP_POINTER_OFFSET
	)

	if x + popup_size.x > right_bound:
		x = (
			global_pointer.x
			- popup_size.x
			- POPUP_POINTER_OFFSET
		)

	x = clampf(
		x,
		left_bound,
		maxf(
			left_bound,
			right_bound - popup_size.x
		)
	)

	y = clampf(
		y,
		top_bound,
		maxf(
			top_bound,
			bottom_bound - popup_size.y
		)
	)

	tooth_editor_panel.position = (
		Vector2(x, y)
		- overlay_rect.position
	)

	tooth_editor_panel.move_to_front()


func _close_tooth_popup() -> void:
	tooth_editor_panel.hide()


# --------------------------------------------------
# Odontogram fullscreen
# --------------------------------------------------

func _toggle_visualization_fullscreen() -> void:
	if visualization_expanded:
		_restore_visualization_layout()
	else:
		_expand_visualization()


func _expand_visualization() -> void:
	if visualization_expanded:
		return

	# If the comparison is open, close it before
	# entering the existing 3D fullscreen mode.
	if comparison_open:
		_close_comparison_overlay()

	previous_navigation_visibility = (
		navigation_bar.visible
	)

	previous_information_visibility = (
		information_panel.visible
	)

	previous_treatment_bar_visibility = (
		treatment_options_bar.visible
	)

	previous_split_offset = (
		main_layout.split_offset
	)

	visualization_expanded = true
	panning = false

	navigation_bar.hide()
	information_panel.hide()
	treatment_options_bar.hide()

	fullscreen_button.text = "Restore"

	fullscreen_button.tooltip_text = (
		"Restore split layout (Esc)"
	)

	_close_tooth_popup()


func _restore_visualization_layout() -> void:
	if not visualization_expanded:
		return

	visualization_expanded = false
	panning = false

	navigation_bar.visible = (
		previous_navigation_visibility
	)

	information_panel.visible = (
		previous_information_visibility
	)

	treatment_options_bar.visible = (
		previous_treatment_bar_visibility
	)

	main_layout.split_offset = (
		previous_split_offset
	)

	fullscreen_button.text = "Expand"

	fullscreen_button.tooltip_text = (
		"Expand 3D visualization"
	)

	_close_tooth_popup()


# --------------------------------------------------
# Mouse and keyboard input
# --------------------------------------------------

func _input(event: InputEvent) -> void:
	if event is InputEventKey:
		var key_event := event as InputEventKey

		if (
			key_event.keycode == KEY_ESCAPE
			and key_event.pressed
			and not key_event.echo
		):
			if comparison_open:
				_close_comparison_overlay()
				get_viewport().set_input_as_handled()
				return

			if visualization_expanded:
				_restore_visualization_layout()
				get_viewport().set_input_as_handled()
				return

			if tooth_editor_panel.visible:
				_close_tooth_popup()
				get_viewport().set_input_as_handled()
				return

	if comparison_open:
		panning = false
		return

	if event is InputEventMouseButton:
		var mouse_event := event as InputEventMouseButton

		if mouse_event.button_index == MOUSE_BUTTON_LEFT:
			if mouse_event.pressed:
				var mouse_position: Vector2 = (
					mouse_event.position
				)

				var inside_viewport: bool = (
					viewport_container.get_global_rect()
					.has_point(mouse_position)
				)

				var over_toolbar: bool = (
					bottom_toolbar.get_global_rect()
					.has_point(mouse_position)
				)

				var over_gizmo: bool = (
					rotation_gizmo.get_global_rect()
					.has_point(mouse_position)
				)

				var over_fullscreen: bool = (
					fullscreen_button.get_global_rect()
					.has_point(mouse_position)
				)

				var over_help: bool = (
					controls_help_button.get_global_rect()
					.has_point(mouse_position)
				)

				var over_help_popup: bool = (
					controls_popup.visible
					and controls_popup.get_global_rect()
					.has_point(mouse_position)
				)

				var over_tooth_popup: bool = (
					tooth_editor_panel.visible
					and tooth_editor_panel.get_global_rect()
					.has_point(mouse_position)
				)

				panning = (
					inside_viewport
					and not over_toolbar
					and not over_gizmo
					and not over_fullscreen
					and not over_help
					and not over_help_popup
					and not over_tooth_popup
				)
			else:
				panning = false

	if event is InputEventMouseMotion and panning:
		var mouse_event := event as InputEventMouseMotion

		if not viewport_container.get_global_rect().has_point(
			mouse_event.position
		):
			panning = false
			return

		var drag: Vector2 = mouse_event.relative

		var camera_right: Vector3 = (
			dental_camera.global_basis.x
		)

		var camera_up: Vector3 = (
			dental_camera.global_basis.y
		)

		dental_camera.global_position += (
			-camera_right * drag.x
			+ camera_up * drag.y
		) * pan_sensitivity


# --------------------------------------------------
# Existing jaw and camera controls
# --------------------------------------------------

func _on_jaw_opening_slider_value_changed(
	value: float
) -> void:
	odontogram.set_jaw_opening(value / 100.0)


func _on_jaw_visibility_selector_item_selected(
	index: int
) -> void:
	match index:
		0:
			odontogram.show_both_jaws()
		1:
			odontogram.show_upper_jaw()
		2:
			odontogram.show_lower_jaw()


func _on_reset_camera_button_pressed() -> void:
	dental_camera.reset_camera()


func _on_controls_help_button_pressed() -> void:
	if controls_popup.visible:
		controls_popup.hide()
		return

	var maximum_size: Vector2 = (
		visualization_panel.size - Vector2(24, 24)
	)

	controls_popup.size = Vector2(
		minf(520.0, maximum_size.x),
		minf(500.0, maximum_size.y)
	)

	controls_popup.position = (
		visualization_panel.size
		- controls_popup.size
	) / 2.0

	controls_popup.show()
	
	
# --------------------------------------------------
# Shared navigation header
# --------------------------------------------------

func _setup_navigation_header() -> void:
	navigation_bar.custom_minimum_size.y = 54

	# Use a dedicated background because an HBoxContainer
	# does not draw a panel StyleBox.
	navigation_background = ColorRect.new()
	navigation_background.name = "NavigationBackground"
	navigation_background.color = Color("#172536")
	navigation_background.mouse_filter = (
		Control.MOUSE_FILTER_IGNORE
	)

	navigation_bar.add_child(navigation_background)
	navigation_bar.move_child(navigation_background, 0)

	navigation_background.set_anchors_and_offsets_preset(
		Control.PRESET_FULL_RECT
	)

	# Existing buttons remain in the scene.
	for button in [
		clinical_tab,
		treatment_tab,
		patient_tab
	]:
		button.custom_minimum_size.y = 34
		button.size_flags_vertical = (
			Control.SIZE_SHRINK_CENTER
		)

		button.add_theme_font_size_override(
			"font_size", 13
		)

	# Push the patient name to the right.
	var spacer := Control.new()
	spacer.name = "NavigationSpacer"
	spacer.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)
	spacer.mouse_filter = (
		Control.MOUSE_FILTER_IGNORE
	)
	navigation_bar.add_child(spacer)

	patient_name_label = Label.new()
	patient_name_label.name = "PatientNameInNavigation"
	patient_name_label.horizontal_alignment = (
		HORIZONTAL_ALIGNMENT_RIGHT
	)
	patient_name_label.vertical_alignment = (
		VERTICAL_ALIGNMENT_CENTER
	)
	patient_name_label.size_flags_vertical = (
		Control.SIZE_SHRINK_CENTER
	)
	patient_name_label.mouse_filter = (
		Control.MOUSE_FILTER_IGNORE
	)
	patient_name_label.add_theme_font_size_override(
		"font_size", 13
	)
	patient_name_label.add_theme_color_override(
		"font_color", Color("#E3ECF6")
	)
	navigation_bar.add_child(patient_name_label)
	
	var credits_spacer := Control.new()
	credits_spacer.custom_minimum_size.x = 16
	navigation_bar.add_child(credits_spacer)

	var credits_button := Button.new()
	credits_button.name = "CreditsAndLicensesButton"
	credits_button.text = "Credits and Licenses"
	credits_button.custom_minimum_size.y = 30
	credits_button.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	credits_button.add_theme_font_size_override("font_size", 11)
	credits_button.tooltip_text = "View media credits and licenses"

	credits_button.pressed.connect(_open_credits)
	navigation_bar.add_child(credits_button)

	var right_padding := Control.new()
	right_padding.custom_minimum_size.x = 14
	right_padding.mouse_filter = (
		Control.MOUSE_FILTER_IGNORE
	)
	navigation_bar.add_child(right_padding)

	_refresh_patient_name_header()


func _refresh_patient_name_header() -> void:
	if patient_name_label == null:
		return

	var connector: Node = get_node_or_null(
		"CDSSConnection"
	)

	if connector == null:
		patient_name_label.text = ""
		return

	var value: Variant = connector.get(
		"patient_display_name"
	)

	patient_name_label.text = (
		str(value).strip_edges()
		if value != null
		else ""
	)


# --------------------------------------------------
# Full-workspace treatment comparison overlay
# --------------------------------------------------

func _setup_comparison_overlay() -> void:
	comparison_panel = PanelContainer.new()
	comparison_panel.name = "TreatmentComparisonOverlay"

	comparison_panel.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)
	comparison_panel.size_flags_vertical = (
		Control.SIZE_EXPAND_FILL
	)

	var style := StyleBoxFlat.new()
	style.bg_color = Color("#1B2939")
	style.border_color = Color("#405168")
	style.set_border_width_all(1)
	style.set_corner_radius_all(8)

	style.content_margin_left = 14
	style.content_margin_right = 14
	style.content_margin_top = 12
	style.content_margin_bottom = 12

	comparison_panel.add_theme_stylebox_override(
		"panel", style
	)

	# The overlay occupies MainLayout's space in AppLayout.
	# It does not share height with the odontogram.
	$AppLayout.add_child(comparison_panel)
	$AppLayout.move_child(
		comparison_panel,
		main_layout.get_index() + 1
	)

	var overlay_column := VBoxContainer.new()
	overlay_column.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)
	overlay_column.size_flags_vertical = (
		Control.SIZE_EXPAND_FILL
	)
	overlay_column.add_theme_constant_override(
		"separation", 8
	)
	comparison_panel.add_child(overlay_column)

	var overlay_header := HBoxContainer.new()
	overlay_header.add_theme_constant_override(
		"separation", 10
	)
	overlay_column.add_child(overlay_header)

	var heading := Label.new()
	heading.text = "Treatment comparison"
	heading.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)
	heading.add_theme_font_size_override(
		"font_size", 17
	)
	heading.add_theme_color_override(
		"font_color", Color("#E5EDF7")
	)
	overlay_header.add_child(heading)

	comparison_close_button = Button.new()
	comparison_close_button.text = "Close comparison"
	comparison_close_button.custom_minimum_size.y = 34
	comparison_close_button.add_theme_font_size_override(
		"font_size", 12
	)
	comparison_close_button.pressed.connect(
		_close_comparison_overlay
	)
	overlay_header.add_child(comparison_close_button)

	comparison_content = VBoxContainer.new()
	comparison_content.name = "ComparisonContent"
	comparison_content.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)
	comparison_content.size_flags_vertical = (
		Control.SIZE_EXPAND_FILL
	)
	comparison_content.add_theme_constant_override(
		"separation", 6
	)
	overlay_column.add_child(comparison_content)

	comparison_panel.hide()

	treatment_page.set_comparison_target(
		comparison_content
	)


func _open_comparison_overlay() -> void:
	if not treatment_results_ready:
		return

	if visualization_expanded:
		_restore_visualization_layout()

	comparison_open = true
	active_page_name = "TreatmentComparisonPage"

	# The header remains visible; the two-panel
	# workspace is replaced by the comparison.
	main_layout.hide()
	comparison_panel.show()
	navigation_bar.show()

	_update_navigation_appearance(
		"TreatmentComparisonPage"
	)

	panning = false
	_close_tooth_popup()


func _close_comparison_overlay() -> void:
	comparison_open = false

	if comparison_panel != null:
		comparison_panel.hide()

	main_layout.show()
	navigation_bar.show()

	# Return to the ordinary Treatment Options workspace.
	active_page_name = "TreatmentComparisonPage"

	_update_navigation_appearance(
		"TreatmentComparisonPage"
	)


# --------------------------------------------------
# Main page navigation
# --------------------------------------------------

func _setup_page_navigation() -> void:
	clinical_tab.pressed.connect(
		func() -> void:
			_show_cdss_page(
				"ClinicalAssessmentPage",
				"Clinical Assessment"
			)
	)

	treatment_tab.pressed.connect(
		func() -> void:
			_show_cdss_page(
				"TreatmentComparisonPage",
				"Treatment Options"
			)
	)

	patient_tab.pressed.connect(
		func() -> void:
			_show_cdss_page(
				"PatientInformationPage",
				"After Visit Summary"
			)
	)


func _show_cdss_page(
	page_name: String,
	heading: String
) -> void:
	if (
		page_name == "TreatmentComparisonPage"
		and not treatment_results_ready
	):
		return

	# Close any comparison currently covering
	# the ordinary workspace.
	if comparison_open:
		comparison_open = false
		comparison_panel.hide()

	main_layout.show()

	active_page_name = page_name
	page_heading.text = heading

	page_heading.visible = (
		page_name != "TreatmentComparisonPage"
	)

	for page in page_container.get_children():
		page.visible = (
			page.name == page_name
		)

	treatment_options_bar.hide()
	navigation_bar.show()

	_update_navigation_appearance(page_name)

	if page_name == "PatientInformationPage":
		var avs_page: Node = page_container.get_node(
        	"PatientInformationPage"
	)
		avs_page.refresh_document(
			$CDSSConnection,
			treatment_page,
			tooth_controller
	)

# --------------------------------------------------
# Navigation appearance
# --------------------------------------------------

func _update_navigation_appearance(
	page_name: String
) -> void:
	var tabs: Dictionary = {
		"ClinicalAssessmentPage": clinical_tab,
		"TreatmentComparisonPage": treatment_tab,
		"PatientInformationPage": patient_tab
	}

	for name: String in tabs:
		var button: Button = tabs[name]
		var active: bool = (
			name == page_name
		)

		var normal := StyleBoxFlat.new()
		normal.bg_color = (
			Color("#2868C9")
			if active
			else Color("#172536")
		)
		normal.border_color = (
			Color("#5799FA")
			if active
			else Color("#172536")
		)
		normal.set_border_width_all(1)
		normal.set_corner_radius_all(7)

		normal.content_margin_left = 12
		normal.content_margin_right = 12
		normal.content_margin_top = 7
		normal.content_margin_bottom = 7

		button.add_theme_stylebox_override(
			"normal", normal
		)

		var hover: StyleBoxFlat = normal.duplicate()
		hover.bg_color = (
			Color("#367CE5")
			if active
			else Color("#283C54")
		)
		button.add_theme_stylebox_override(
			"hover", hover
		)

		button.add_theme_color_override(
			"font_color",
			Color.WHITE
			if active
			else Color("#C4D0DE")
		)
		button.add_theme_color_override(
			"font_hover_color", Color.WHITE
		)


# --------------------------------------------------
# Evaluation response
# --------------------------------------------------

func _on_evaluation_completed(
	data: Dictionary
) -> void:
	_refresh_patient_name_header()

	var accepted: bool = (
		treatment_page.display_evaluation(
			data,
			tooth_controller
		)
	)

	if not accepted:
		treatment_results_ready = false
		treatment_tab.disabled = true
		_close_comparison_overlay()
		return

	treatment_results_ready = true
	treatment_tab.disabled = false

	_show_cdss_page(
		"TreatmentComparisonPage",
		"Treatment Options"
	)


func _on_clinical_case_loaded(
	_data: Dictionary
) -> void:
	_refresh_patient_name_header()

	treatment_results_ready = false
	treatment_tab.disabled = true

	treatment_page.clear_evaluation()

	if comparison_open:
		comparison_open = false
		comparison_panel.hide()
		main_layout.show()

	if active_page_name == "TreatmentComparisonPage":
		_show_cdss_page(
			"ClinicalAssessmentPage",
			"Clinical Assessment"
		)


# --------------------------------------------------
# Treatment comparison state
# --------------------------------------------------

func _on_comparison_mode_changed(
	enabled: bool
) -> void:
	if enabled:
		_open_comparison_overlay()
	else:
		_close_comparison_overlay()
		
		
		

# --------------------------------------------------
# Central media credits and licenses
# --------------------------------------------------

func _open_credits(media_ids: Array = []) -> void:
	var connector: Node = $CDSSConnection
	var catalogue: Dictionary = connector.media_catalogue

	var credits_popup := PopupPanel.new()
	credits_popup.name = "CreditsAndLicensesPopup"
	credits_popup.exclusive = true

	var window_size := get_window().size

	var credits_size := Vector2i(
   		mini(680, int(window_size.x * 0.85)),
		mini(600, int(window_size.y * 0.80))
	)

	credits_popup.wrap_controls = false
	credits_popup.min_size = Vector2i.ZERO
	credits_popup.max_size = credits_size

	add_child(credits_popup)

	credits_popup.popup_hide.connect(
		credits_popup.queue_free
	)

	var popup_style := StyleBoxFlat.new()
	popup_style.bg_color = Color("#253346")
	popup_style.border_color = Color("#405168")
	popup_style.set_border_width_all(1)
	popup_style.set_corner_radius_all(8)
	popup_style.set_content_margin_all(16)

	credits_popup.add_theme_stylebox_override(
		"panel",
		popup_style
	)

	var layout := VBoxContainer.new()
	layout.add_theme_constant_override("separation", 12)
	credits_popup.add_child(layout)

	# Header
	var header := HBoxContainer.new()
	header.add_theme_constant_override("separation", 10)
	layout.add_child(header)

	var heading := Label.new()
	heading.text = "Credits and Licenses"
	heading.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	heading.add_theme_font_size_override("font_size", 18)
	heading.add_theme_color_override(
		"font_color",
		Color("#E5EDF7")
	)
	header.add_child(heading)

	var close_button := Button.new()
	close_button.text = "X"
	close_button.custom_minimum_size = Vector2(30, 30)
	close_button.pressed.connect(credits_popup.hide)
	header.add_child(close_button)

	var introduction := Label.new()
	introduction.text = (
		"Media sources, creators, licenses and modifications "
		+ "for visual materials used in this application."
	)
	introduction.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	introduction.add_theme_font_size_override(
		"font_size", 11
	)
	introduction.add_theme_color_override(
		"font_color", Color("#B9C7D8")
	)
	layout.add_child(introduction)

	# Scrollable catalogue
	var scroll := ScrollContainer.new()

	scroll.custom_minimum_size = Vector2(
		620,
		mini(500, int(credits_size.y * 0.8))
	)

	scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.size_flags_vertical = Control.SIZE_SHRINK_BEGIN

	scroll.horizontal_scroll_mode = (
		ScrollContainer.SCROLL_MODE_DISABLED
	)

	scroll.vertical_scroll_mode = (
		ScrollContainer.SCROLL_MODE_AUTO
	)

	layout.add_child(scroll)

	var content := VBoxContainer.new()
	content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	content.add_theme_constant_override("separation", 12)
	scroll.add_child(content)

	if catalogue.is_empty():
		_credits_add_label(
			content,
			"Media catalogue is not currently available.",
			12
		)
	else:
		for category in ["3d_model", "image"]:
			var entries: Array = []

			for media_id in catalogue:
				if (
					not media_ids.is_empty()
					and not media_ids.has(media_id)
				):
					continue

				var entry: Variant = catalogue[media_id]

				if not entry is Dictionary:
					continue

				if str(entry.get("media_type", "")) == category:
					entries.append(entry)

			if entries.is_empty():
				continue

			entries.sort_custom(
				func(a, b):
					return (
						str(a.get("title", "")).nocasecmp_to(
							str(b.get("title", ""))
						) < 0
					)
			)

			var section_title := (
				"3D Models"
				if category == "3d_model"
				else "Clinical Images and Illustrations"
			)

			_credits_add_label(
				content,
				section_title,
				15
			)

			for entry in entries:
				_credits_add_entry(content, entry)

	credits_popup.popup_centered(credits_size)
	scroll.set_deferred("scroll_vertical", 0)

func _credits_add_entry(
	parent: VBoxContainer,
	media: Dictionary
) -> void:
	var panel := PanelContainer.new()
	parent.add_child(panel)

	var style := StyleBoxFlat.new()
	style.bg_color = Color("#1B2939")
	style.border_color = Color("#405168")
	style.set_border_width_all(1)
	style.set_corner_radius_all(7)
	style.set_content_margin_all(12)
	panel.add_theme_stylebox_override("panel", style)

	var content := VBoxContainer.new()
	content.add_theme_constant_override("separation", 5)
	panel.add_child(content)

	_credits_add_label(
		content,
		str(media.get("title", "Untitled media")),
		14
	)

	for field in [
		["creator", "Creator"],
		["license_name", "License"],
		["modifications", "Modifications"],
		["notes", "Notes"]
	]:
		var raw_value: Variant = media.get(field[0])

		if raw_value == null:
			continue

		var value := str(raw_value).strip_edges()

		if value.is_empty():
			continue

		_credits_add_label(
			content,
			field[1] + ": " + value,
			11
		)

	var links := HBoxContainer.new()
	links.add_theme_constant_override("separation", 8)
	content.add_child(links)

	_credits_add_link(
		links,
		"Original source",
		media.get("source_url")
	)

	_credits_add_link(
		links,
		"License details",
		media.get("license_url")
	)


func _credits_add_label(
	parent: Node,
	value: String,
	font_size: int
) -> void:
	var label := Label.new()
	label.text = value
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL

	label.add_theme_font_size_override(
		"font_size",
		font_size
	)

	label.add_theme_color_override(
		"font_color",
		Color("#E5EDF7")
		if font_size >= 14
		else Color("#B9C7D8")
	)

	parent.add_child(label)


func _credits_add_link(
	parent: HBoxContainer,
	link_text: String,
	raw_url: Variant
) -> void:
	if raw_url == null:
		return

	var url := str(raw_url).strip_edges()

	if not (
		url.begins_with("https://")
		or url.begins_with("http://")
	):
		return

	var button := Button.new()
	button.text = link_text
	button.add_theme_font_size_override("font_size", 11)

	button.pressed.connect(
		func():
			OS.shell_open(url)
	)

	parent.add_child(button)
