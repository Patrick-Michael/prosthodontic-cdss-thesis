
extends Camera3D

@export var movement_speed: float = 48.0
@export var sprint_multiplier: float = 3.0
@export var keyboard_rotation_speed: float = 90.0
@export var mouse_sensitivity: float = 0.003
@export var zoom_step: float = 5.0

var initial_transform: Transform3D
var right_mouse_held: bool = false


func _ready() -> void:
	initial_transform = transform


func _mouse_is_inside_viewport() -> bool:
	var viewport := get_viewport()

	var mouse_position := viewport.get_mouse_position()
	var viewport_size := viewport.get_visible_rect().size

	return (
		mouse_position.x >= 0.0
		and mouse_position.y >= 0.0
		and mouse_position.x < viewport_size.x
		and mouse_position.y < viewport_size.y
	)


func _text_control_has_focus() -> bool:
	var focused := get_tree().root.gui_get_focus_owner()

	if focused == null:
		return false

	return (
		focused is LineEdit
		or focused is TextEdit
		or focused is CodeEdit
	)


func _camera_keyboard_active() -> bool:
	return (
		_mouse_is_inside_viewport()
		and not _text_control_has_focus()
	)


func _process(delta: float) -> void:
	if not _camera_keyboard_active():
		return

	var direction := Vector3.ZERO

	# Camera-relative movement.
	if Input.is_physical_key_pressed(KEY_W):
		direction.z -= 1.0

	if Input.is_physical_key_pressed(KEY_S):
		direction.z += 1.0

	if Input.is_physical_key_pressed(KEY_A):
		direction.x -= 1.0

	if Input.is_physical_key_pressed(KEY_D):
		direction.x += 1.0

	var movement := global_transform.basis * direction

	# Vertical movement.
	if Input.is_physical_key_pressed(KEY_SHIFT):
		movement.y += 1.0

	if Input.is_physical_key_pressed(KEY_CTRL):
		movement.y -= 1.0

	var current_speed := movement_speed

	if Input.is_physical_key_pressed(KEY_SPACE):
		current_speed *= sprint_multiplier

	if movement.length_squared() > 0.0:
		global_position += (
			movement.normalized()
			* current_speed
			* delta
		)

	# Horizontal keyboard rotation.
	if Input.is_physical_key_pressed(KEY_Q):
		rotate_y(
			deg_to_rad(keyboard_rotation_speed) * delta
		)

	if Input.is_physical_key_pressed(KEY_E):
		rotate_y(
			-deg_to_rad(keyboard_rotation_speed) * delta
		)


func _input(event: InputEvent) -> void:
	var inside := _mouse_is_inside_viewport()

	if event is InputEventMouseButton:
		var mouse_event := event as InputEventMouseButton

		if mouse_event.button_index == MOUSE_BUTTON_RIGHT:
			if mouse_event.pressed:
				right_mouse_held = inside
			else:
				right_mouse_held = false

		if inside and mouse_event.pressed:
			if mouse_event.button_index == MOUSE_BUTTON_WHEEL_UP:
				global_position -= (
					global_transform.basis.z * zoom_step
				)

			elif mouse_event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
				global_position += (
					global_transform.basis.z * zoom_step
				)

	if event is InputEventMouseMotion:
		if not inside:
			right_mouse_held = false
			return

		if right_mouse_held:
			var mouse_motion := event as InputEventMouseMotion

			rotate_y(
				-mouse_motion.screen_relative.x
				* mouse_sensitivity
			)

			rotation.x -= (
				mouse_motion.screen_relative.y
				* mouse_sensitivity
			)

			rotation.x = clampf(
				rotation.x,
				deg_to_rad(-85.0),
				deg_to_rad(85.0)
			)

	if event is InputEventKey:
		var key_event := event as InputEventKey

		if (
			_camera_keyboard_active()
			and key_event.physical_keycode == KEY_R
			and key_event.pressed
			and not key_event.echo
		):
			reset_camera()


func reset_camera() -> void:
	transform = initial_transform
	right_mouse_held = false
