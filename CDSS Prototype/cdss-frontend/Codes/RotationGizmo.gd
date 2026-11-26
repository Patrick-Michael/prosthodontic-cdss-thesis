
extends Control

@export var model_root: Node3D
@export var middle_drag_sensitivity: float = 0.35

@onready var x_slider: VSlider = $AxisSliders/XGroup/XRotation
@onready var y_slider: VSlider = $AxisSliders/YGroup/YRotation
@onready var z_slider: VSlider = $AxisSliders/ZGroup/ZRotation

@onready var viewport_container: Control = (
	get_parent().get_node("ViewportContainer")
)

@onready var tooth_editor: Control = (
	get_parent().get_node(
		"VisualizationOverlay/ToothEditorPanel"
	)
)

@onready var bottom_toolbar: Control = (
	get_parent().get_node(
		"VisualizationOverlay/BottomToolbar"
	)
)

var initial_rotation: Vector3
var middle_dragging: bool = false


func _ready() -> void:
	if model_root == null:
		push_error(
			"RotationGizmo: Model Root is not assigned."
		)
		return

	initial_rotation = model_root.rotation_degrees

	x_slider.value_changed.connect(_on_rotation_changed)
	y_slider.value_changed.connect(_on_rotation_changed)
	z_slider.value_changed.connect(_on_rotation_changed)


func _input(event: InputEvent) -> void:
	if model_root == null:
		return

	if event is InputEventMouseButton:
		var mouse_event := event as InputEventMouseButton

		if mouse_event.button_index != MOUSE_BUTTON_MIDDLE:
			return

		if not mouse_event.pressed:
			middle_dragging = false
			return

		var pointer: Vector2 = mouse_event.position

		middle_dragging = (
			viewport_container.get_global_rect().has_point(pointer)
			and not get_global_rect().has_point(pointer)
			and not (
				tooth_editor.visible
				and tooth_editor.get_global_rect().has_point(pointer)
			)
			and not bottom_toolbar.get_global_rect().has_point(pointer)
		)

	elif event is InputEventMouseMotion and middle_dragging:
		var motion := event as InputEventMouseMotion

		# Horizontal mouse movement controls Y-axis rotation.
		var change: float = (
   		 motion.relative.x * middle_drag_sensitivity
)		

		y_slider.value = clampf(
			y_slider.value + change,
			y_slider.min_value,
			y_slider.max_value
		)


func _on_rotation_changed(_value: float) -> void:
	if model_root == null:
		return

	model_root.rotation_degrees = initial_rotation + Vector3(
		x_slider.value,
		y_slider.value,
		z_slider.value
	)


func reset_model_rotation() -> void:
	if model_root == null:
		return

	middle_dragging = false

	x_slider.set_value_no_signal(0.0)
	y_slider.set_value_no_signal(0.0)
	z_slider.set_value_no_signal(0.0)

	model_root.rotation_degrees = initial_rotation


func _on_reset_rotation_button_pressed() -> void:
	reset_model_rotation()
