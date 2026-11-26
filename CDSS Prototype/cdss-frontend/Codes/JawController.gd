
extends Node3D

@onready var upper_jaw: Node3D = $ModelRotationRoot/clinical_odontogram/UpperJawRoot
@onready var lower_jaw: Node3D = $ModelRotationRoot/clinical_odontogram/LowerJawRoot

# The closed-mouth rotation is preserved from the imported model.
var closed_rotation: Vector3

# Adjust this after testing the direction and desired opening.
@export var maximum_opening_degrees: float = 50.0


func _ready() -> void:
	closed_rotation = lower_jaw.rotation_degrees


func set_jaw_opening(amount: float) -> void:
	# amount ranges from 0.0 (closed) to 1.0 (fully open).
	amount = clampf(amount, 0.0, 1.0)

	var target_rotation := closed_rotation
	target_rotation.x += maximum_opening_degrees * amount

	var tween := create_tween()
	tween.tween_property(lower_jaw, "rotation_degrees", target_rotation, 0.3)


func show_both_jaws() -> void:
	upper_jaw.visible = true
	lower_jaw.visible = true


func show_upper_jaw() -> void:
	upper_jaw.visible = true
	lower_jaw.visible = false


func show_lower_jaw() -> void:
	upper_jaw.visible = false
	lower_jaw.visible = true


func _on_jaw_opening_slider_value_changed(value: float) -> void:
	set_jaw_opening(value / 100.0)


func _on_reset_camera_button_pressed() -> void:
	var camera := get_node("../DentalCamera") as Camera3D
	camera.reset_camera()


func _on_jaw_visibility_selector_item_selected(index: int) -> void:
	match index:
		0:
			show_both_jaws()
		1:
			show_upper_jaw()
		2:
			show_lower_jaw()
