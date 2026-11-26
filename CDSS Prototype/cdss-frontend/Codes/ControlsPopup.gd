
extends PanelContainer

const CONTROLS := [
	["W / A / S / D", "Move camera"],
	["Shift", "Move camera up"],
	["Ctrl", "Move camera down"],
	["Space + movement", "Move 3× faster"],
	["Q / E", "Rotate camera left / right"],
	["Right mouse drag", "Look around"],
	["Left-drag empty space", "Pan camera"],
	["Mouse wheel", "Zoom in / out"],
	["Middle mouse drag", "Rotate dental model horizontally"],
	["R", "Reset camera"],
	["X / Y / Z sliders", "Rotate dental model"],
	["Reset Rotation", "Restore model orientation"],
	["Jaw opening slider", "Open / close mouth"],
	["Visible jaws", "Show both, upper or lower"]
]


func _ready() -> void:
	var margin: MarginContainer = $MarginContainer



	# Main vertical layout.
	var layout := VBoxContainer.new()
	layout.name = "LegendLayout"
	layout.add_theme_constant_override("separation", 14)
	margin.add_child(layout)

	# Heading.
	var heading := Label.new()
	heading.text = "Odontogram controls"
	heading.add_theme_font_size_override("font_size", 17)
	layout.add_child(heading)

	# Automatically aligned two-column grid.
	var grid := GridContainer.new()
	grid.name = "ControlsGrid"
	grid.columns = 2
	grid.add_theme_constant_override("h_separation", 28)
	grid.add_theme_constant_override("v_separation", 9)
	layout.add_child(grid)

	# Generate each control-description pair.
	for entry in CONTROLS:
		var key_label := Label.new()
		key_label.text = entry[0]
		key_label.add_theme_font_size_override("font_size", 14)
		key_label.add_theme_color_override(
			"font_color",
			Color("#DDDDDD")
		)
		grid.add_child(key_label)

		var action_label := Label.new()
		action_label.text = entry[1]
		action_label.add_theme_font_size_override("font_size", 14)
		grid.add_child(action_label)
