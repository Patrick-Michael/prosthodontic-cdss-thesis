
extends Node3D

signal tooth_selected(fdi: String)
signal tooth_popup_requested(fdi: String, viewport_position: Vector2)

const FMA_TO_FDI: Dictionary = {
	"FMA55681": "11",
	"FMA55680": "12",
	"FMA55798": "13",
	"FMA55689": "14",
	"FMA55688": "15",
	"FMA55698": "16",
	"FMA55697": "17",

	"FMA55682": "21",
	"FMA55683": "22",
	"FMA55799": "23",
	"FMA55690": "24",
	"FMA55691": "25",
	"FMA55699": "26",
	"FMA55700": "27",

	"FMA57143": "31",
	"FMA57141": "32",
	"FMA55687": "33",
	"FMA55693": "34",
	"FMA55692": "35",
	"FMA55704": "36",
	"FMA55703": "37",

	"FMA57142": "41",
	"FMA57140": "42",
	"FMA55686": "43",
	"FMA55694": "44",
	"FMA55695": "45",
	"FMA55705": "46",
	"FMA55706": "47"
}

const TOOTH_TYPES: Array[String] = [
	"central incisor",
	"lateral incisor",
	"canine",
	"first premolar",
	"second premolar",
	"first molar",
	"second molar"
]

const TOOTH_COLLISION_LAYER: int = 2
const CLICK_DRAG_THRESHOLD: float = 6.0
const RAY_DISTANCE: float = 1000.0

var teeth: Dictionary = {}
var selected_fdi: String = ""

var left_mouse_held: bool = false
var left_press_position: Vector2 = Vector2.ZERO
var left_dragged: bool = false

var right_mouse_held: bool = false
var right_press_position: Vector2 = Vector2.ZERO
var right_dragged: bool = false

var previous_overlays: Dictionary = {}
var selection_material: StandardMaterial3D
var abutment_overlays: Dictionary = {}
var abutment_material: StandardMaterial3D


# Animated visual indicators for selected missing spans.
# These do not change tooth presence or clinical state.
var span_ghosts: Dictionary = {}
var span_ghost_material: ShaderMaterial

@onready var model: Node3D = (
	get_parent().get_node(
		"ModelRotationRoot/clinical_odontogram"
	)
)

@onready var dental_camera: Camera3D = (
	get_parent().get_parent().get_node("DentalCamera")
)


# --------------------------------------------------
# Initialization
# --------------------------------------------------

func _ready() -> void:
	_build_tooth_registry()
	_build_tooth_collisions()
	register_gingival_covers()


func _build_tooth_registry() -> void:
	teeth.clear()

	for fma: String in FMA_TO_FDI:
		var fdi: String = FMA_TO_FDI[fma]

		teeth[fdi] = {
			"fma": fma,
			"components": [],
			"colliders": [],
			"present": true
		}

	_register_components(model)

	for fdi: String in teeth:
		if teeth[fdi]["components"].is_empty():
			push_warning(
				"No anatomical components found for FDI " + fdi
			)

	print(
		"Tooth registry initialized: ",
		teeth.size(),
		" FDI positions."
	)


func _register_components(current_node: Node) -> void:
	for child in current_node.get_children():
		if child is MeshInstance3D:
			var fma: String = String(child.name).split("-")[0]

			if FMA_TO_FDI.has(fma):
				var fdi: String = FMA_TO_FDI[fma]
				teeth[fdi]["components"].append(child)

		_register_components(child)


# --------------------------------------------------
# Collision bodies
# --------------------------------------------------

func _build_tooth_collisions() -> void:
	var collision_count: int = 0

	for fdi: String in teeth:
		for component: MeshInstance3D in teeth[fdi]["components"]:
			if component.mesh == null:
				continue

			var shape: ConcavePolygonShape3D = (
				component.mesh.create_trimesh_shape()
			)

			if shape == null:
				continue

			var body := StaticBody3D.new()
			body.name = "ToothCollision"
			body.collision_layer = TOOTH_COLLISION_LAYER
			body.collision_mask = 0
			body.set_meta("fdi", fdi)

			# The collider follows the anatomical component,
			# including jaw opening and model rotation.
			component.add_child(body)

			var collision_shape := CollisionShape3D.new()
			collision_shape.name = "CollisionShape3D"
			collision_shape.shape = shape

			body.add_child(collision_shape)

			teeth[fdi]["colliders"].append(body)
			collision_count += 1

	print(
		"Tooth collision bodies created: ",
		collision_count
	)


# --------------------------------------------------
# Mouse interaction
# --------------------------------------------------

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mouse_event := event as InputEventMouseButton

		match mouse_event.button_index:
			MOUSE_BUTTON_LEFT:
				_handle_left_button(mouse_event)

			MOUSE_BUTTON_RIGHT:
				_handle_right_button(mouse_event)

	elif event is InputEventMouseMotion:
		var motion := event as InputEventMouseMotion

		if left_mouse_held:
			if (
				motion.position.distance_to(left_press_position)
				> CLICK_DRAG_THRESHOLD
			):
				left_dragged = true

		if right_mouse_held:
			if (
				motion.position.distance_to(right_press_position)
				> CLICK_DRAG_THRESHOLD
			):
				right_dragged = true


func _handle_left_button(event: InputEventMouseButton) -> void:
	if event.pressed:
		left_mouse_held = true
		left_dragged = false
		left_press_position = event.position
		return

	if left_mouse_held and not left_dragged:
		var fdi: String = _get_tooth_at_position(event.position)

		if fdi != "":
			select_tooth(fdi)

	left_mouse_held = false
	left_dragged = false


func _handle_right_button(event: InputEventMouseButton) -> void:
	if event.pressed:
		right_mouse_held = true
		right_dragged = false
		right_press_position = event.position
		return

	if right_mouse_held and not right_dragged:
		var fdi: String = _get_tooth_at_position(event.position)

		if fdi != "":
			select_tooth(fdi)

			tooth_popup_requested.emit(
				fdi,
				event.position
			)

	right_mouse_held = false
	right_dragged = false


# --------------------------------------------------
# Raycasting
# --------------------------------------------------

func _get_tooth_at_position(
	screen_position: Vector2
) -> String:
	var origin: Vector3 = (
		dental_camera.project_ray_origin(screen_position)
	)

	var direction: Vector3 = (
		dental_camera.project_ray_normal(screen_position)
	)

	var query := PhysicsRayQueryParameters3D.create(
		origin,
		origin + direction * RAY_DISTANCE
	)

	query.collision_mask = TOOTH_COLLISION_LAYER

	var result: Dictionary = (
		get_world_3d().direct_space_state.intersect_ray(query)
	)

	if result.is_empty():
		return ""

	var collider: Object = result["collider"]

	if not collider.has_meta("fdi"):
		return ""

	var fdi: String = str(collider.get_meta("fdi"))

	if not is_tooth_present(fdi):
		return ""

	return fdi


# --------------------------------------------------
# Tooth identification
# --------------------------------------------------

func get_tooth_components(fdi: String) -> Array:
	if not teeth.has(fdi):
		return []

	return teeth[fdi]["components"]


func get_tooth_name(fdi: String) -> String:
	if not teeth.has(fdi):
		return ""

	var quadrant: int = int(fdi.substr(0, 1))
	var position: int = int(fdi.substr(1, 1))

	if quadrant < 1 or quadrant > 4:
		return ""

	if position < 1 or position > 7:
		return ""

	var arch: String = (
		"Upper" if quadrant <= 2 else "Lower"
	)

	var side: String = (
		"right"
		if quadrant == 1 or quadrant == 4
		else "left"
	)

	return (
		arch + " " + side + " "
		+ TOOTH_TYPES[position - 1]
	)


# --------------------------------------------------
# Existing present-tooth highlighting
# --------------------------------------------------

func _get_selection_material() -> StandardMaterial3D:
	if selection_material == null:
		selection_material = StandardMaterial3D.new()

		selection_material.albedo_color = Color(
			0.35, 0.75, 1.0, 0.30
		)

		selection_material.transparency = (
			BaseMaterial3D.TRANSPARENCY_ALPHA
		)

		selection_material.roughness = 0.65
		selection_material.metallic = 0.0

	return selection_material


func highlight_tooth(fdi: String) -> void:
	clear_highlight()

	if not teeth.has(fdi):
		return

	if not is_tooth_present(fdi):
		return

	for component: MeshInstance3D in get_tooth_components(fdi):
		previous_overlays[component] = (
			component.material_overlay
		)

		component.material_overlay = (
			_get_selection_material()
		)


func clear_highlight() -> void:
	for component in previous_overlays:
		if is_instance_valid(component):
			component.material_overlay = (
				previous_overlays[component]
			)

	previous_overlays.clear()


# --------------------------------------------------
# Treatment-specific abutment highlighting
# --------------------------------------------------

func _get_abutment_material() -> StandardMaterial3D:
	if abutment_material == null:
		abutment_material = StandardMaterial3D.new()
		abutment_material.albedo_color = Color(
			0.12, 0.85, 0.73, 0.4
		)
		abutment_material.transparency = (
			BaseMaterial3D.TRANSPARENCY_ALPHA
		)
		abutment_material.shading_mode = (
			BaseMaterial3D.SHADING_MODE_UNSHADED
		)
		abutment_material.cull_mode = (
			BaseMaterial3D.CULL_DISABLED
		)

	return abutment_material


func set_highlighted_abutments(abutments: Array) -> void:
	clear_abutment_highlights()

	var processed: Dictionary = {}

	for value in abutments:
		var fdi: String = str(value)

		if processed.has(fdi):
			continue

		processed[fdi] = true

		if not teeth.has(fdi):
			push_warning("Unknown abutment: " + fdi)
			continue

		if not is_tooth_present(fdi):
			continue

		var components: Array = _find_outer_tooth_meshes(fdi)

		for component in components:
			if not component is MeshInstance3D:
				continue

			abutment_overlays[component] = component.material_overlay

			# Existing direct tooth selection takes priority.
			if previous_overlays.has(component):
				previous_overlays[component] = _get_abutment_material()
			else:
				component.material_overlay = _get_abutment_material()


func clear_abutment_highlights() -> void:
	for component in abutment_overlays:
		if not is_instance_valid(component):
			continue

		var original: Material = abutment_overlays[component]

		if previous_overlays.has(component):
			previous_overlays[component] = original
		else:
			component.material_overlay = original

	abutment_overlays.clear()

# --------------------------------------------------
# Selection
# --------------------------------------------------

func select_tooth(fdi: String) -> void:
	if not teeth.has(fdi):
		push_warning("Unknown FDI number: " + fdi)
		return

	if not is_tooth_present(fdi):
		return

	selected_fdi = fdi
	highlight_tooth(fdi)

	print(
		"Selected tooth: FDI ",
		fdi,
		" — ",
		get_tooth_name(fdi)
	)

	tooth_selected.emit(fdi)


func clear_selection() -> void:
	selected_fdi = ""
	clear_highlight()


# --------------------------------------------------
# Tooth presence and visibility
# --------------------------------------------------

func set_tooth_present(
	fdi: String,
	present: bool
) -> void:
	if not teeth.has(fdi):
		push_warning("Unknown FDI number: " + fdi)
		return
		
	if not present:
		for component in _find_outer_tooth_meshes(fdi):
			if abutment_overlays.has(component):
				clear_abutment_highlights()
				break

	if selected_fdi == fdi:
		clear_highlight()

	teeth[fdi]["present"] = present

	# Hide the original anatomical meshes for missing teeth.
	for component: MeshInstance3D in teeth[fdi]["components"]:
		component.visible = present

	# Prevent missing teeth from receiving tooth raycasts.
	for collider: StaticBody3D in teeth[fdi]["colliders"]:
		collider.collision_layer = (
			TOOTH_COLLISION_LAYER if present else 0
		)

	if selected_fdi == fdi and present:
		highlight_tooth(fdi)

	# Keep existing gingival-cover behavior unchanged.
	if teeth[fdi].has("gingival_cover"):
		var cover: Node3D = teeth[fdi]["gingival_cover"]
		cover.visible = not present


func is_tooth_present(fdi: String) -> bool:
	if not teeth.has(fdi):
		return false

	return teeth[fdi]["present"]


# --------------------------------------------------
# Visual case-state representation
# --------------------------------------------------

func get_tooth_states() -> Dictionary:
	var states: Dictionary = {}

	for fdi: String in teeth:
		states[fdi] = is_tooth_present(fdi)

	return states


func get_missing_teeth() -> Array[String]:
	var missing: Array[String] = []

	for fdi: String in teeth:
		if not is_tooth_present(fdi):
			missing.append(fdi)

	missing.sort()
	return missing


func restore_tooth_states(states: Dictionary) -> void:
	clear_highlight()

	for fdi: String in states:
		if teeth.has(fdi):
			set_tooth_present(
				fdi,
				bool(states[fdi])
			)

	if (
		selected_fdi != ""
		and is_tooth_present(selected_fdi)
	):
		highlight_tooth(selected_fdi)


# --------------------------------------------------
# Gingival-cover registration
# --------------------------------------------------

func register_gingival_covers() -> void:
	var registered := 0

	for fdi: String in teeth:
		var jaw_root_name := (
			"UpperJawRoot"
			if fdi[0] == "1" or fdi[0] == "2"
			else "LowerJawRoot"
		)

		var root_name := (
			"upper_gingival_covers"
			if jaw_root_name == "UpperJawRoot"
			else "lower_gingival_covers"
		)

		var cover_path := (
			jaw_root_name
			+ "/" + root_name
			+ "/Cover_" + fdi
		)

		var cover := model.get_node_or_null(
			cover_path
		)

		if cover == null:
			push_warning(
				"Missing gingival cover: " + cover_path
			)
			continue

		teeth[fdi]["gingival_cover"] = cover

		cover.visible = (
			not is_tooth_present(fdi)
		)

		registered += 1

	print(
		"Gingival covers registered: ",
		registered
	)


# --------------------------------------------------
# Animated missing-span hologram material
# --------------------------------------------------

func _get_span_ghost_material() -> ShaderMaterial:
	if span_ghost_material != null:
		return span_ghost_material

	var shader := Shader.new()

	shader.code = """
shader_type spatial;
render_mode unshaded, blend_mix, cull_disabled,
	depth_draw_never;

uniform vec4 ghost_color : source_color =
	vec4(0.22, 0.65, 1.0, 1.0);

varying vec3 local_position;

void vertex() {
	local_position = VERTEX;
}

void fragment() {
	float pulse = 0.5 + 0.5 * sin(TIME * 3.0);

	float sweep_position = fract(
		local_position.y * 0.6 - TIME * 0.55
	);

	float sweep = 1.0 - smoothstep(
		0.0,
		0.14,
		abs(sweep_position - 0.5)
	);

	float brightness = 0.55 + pulse * 0.25 + sweep;

	ALBEDO = ghost_color.rgb * brightness;

	EMISSION = ghost_color.rgb * (
		0.35 + sweep * 1.5
	);

	ALPHA = clamp(
		0.24 + pulse * 0.12 + sweep * 0.30,
		0.0,
		0.70
	);
}
"""

	span_ghost_material = ShaderMaterial.new()
	span_ghost_material.shader = shader

	return span_ghost_material


# --------------------------------------------------
# Locate existing enamel or prosthetic outer meshes
# --------------------------------------------------

func _find_outer_tooth_meshes(fdi: String) -> Array:
	var outer_meshes: Array = []

	if not teeth.has(fdi):
		return outer_meshes

	for component in teeth[fdi]["components"]:
		if not component is MeshInstance3D:
			continue

		if component.mesh == null:
			continue

		var component_name: String = (
			str(component.name).to_lower()
		)

		if (
			component_name.ends_with("-enamel")
			or component_name.ends_with("-prosthetic")
		):
			outer_meshes.append(component)

	return outer_meshes


# --------------------------------------------------
# Highlight selected missing spans
# --------------------------------------------------

func set_highlighted_spans(spans: Array) -> void:
	clear_span_highlights()

	var highlighted_fdi: Dictionary = {}

	for span in spans:
		if not span is Array:
			continue

		for tooth in span:
			var fdi: String = str(tooth)

			if highlighted_fdi.has(fdi):
				continue

			if not teeth.has(fdi):
				continue

			# Do not place missing-tooth holograms
			# over teeth recorded as present.
			if is_tooth_present(fdi):
				continue

			highlighted_fdi[fdi] = true

			var outer_meshes: Array = (
				_find_outer_tooth_meshes(fdi)
			)

			if outer_meshes.is_empty():
				push_warning(
					"No outer tooth mesh found for FDI " + fdi
				)
				continue

			for original in outer_meshes:
				var ghost := MeshInstance3D.new()

				ghost.name = "SpanGhost_" + fdi

				# Share existing tooth geometry without
				# modifying the original anatomical mesh.
				ghost.mesh = original.mesh

				ghost.material_override = (
					_get_span_ghost_material()
				)

				ghost.cast_shadow = (
					GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
				)

				ghost.layers = original.layers

				# Position the ghost beside the hidden
				# original tooth mesh, under the same parent.
				# This lets it follow jaw movement.
				original.get_parent().add_child(ghost)
				ghost.transform = original.transform

				if not span_ghosts.has(fdi):
					span_ghosts[fdi] = []

				span_ghosts[fdi].append(ghost)


# --------------------------------------------------
# Clear the missing-span visual selection
# --------------------------------------------------

func clear_span_highlights() -> void:
	for fdi in span_ghosts:
		for ghost in span_ghosts[fdi]:
			if is_instance_valid(ghost):
				ghost.queue_free()

	span_ghosts.clear()
