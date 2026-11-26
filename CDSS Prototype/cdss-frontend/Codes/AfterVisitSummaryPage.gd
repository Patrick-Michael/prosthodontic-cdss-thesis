
extends VBoxContainer

# --------------------------------------------------
# After Visit Summary
#
# Patient-facing preview and printable document.
# Uses existing case, evaluation, knowledge and media.
# No clinical inference is performed here.
# --------------------------------------------------

const INK := Color("#E5EDF7")
const MUTED := Color("#B9C7D8")
const PANEL := Color("#253346")
const BLUE := Color("#294D79")
const BORDER := Color("#405168")

var _connector: Node
var _treatments: Node
var _teeth: Node

var _snapshot: Dictionary = {}

var _content: VBoxContainer
var _print_button: Button
var _message: Label


# --------------------------------------------------
# Initialization
# --------------------------------------------------

func _ready() -> void:
	var placeholder := get_node_or_null(
		"PatientInformationPagePlaceholder"
	)

	if placeholder != null:
		placeholder.hide()

	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	add_theme_constant_override("separation", 10)

	var toolbar := HBoxContainer.new()
	add_child(toolbar)

	_message = Label.new()
	_message.text = (
		"Evaluate a clinical case to prepare the summary."
	)
	_message.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_message.add_theme_color_override("font_color", MUTED)
	toolbar.add_child(_message)

	_print_button = Button.new()
	_print_button.text = "Print / Save as PDF"
	_print_button.disabled = true
	_print_button.pressed.connect(_print_document)
	toolbar.add_child(_print_button)

	var scrolling := ScrollContainer.new()
	scrolling.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scrolling.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scrolling.horizontal_scroll_mode = (
		ScrollContainer.SCROLL_MODE_DISABLED
	)
	add_child(scrolling)

	_content = VBoxContainer.new()
	_content.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_content.add_theme_constant_override("separation", 12)
	scrolling.add_child(_content)


# --------------------------------------------------
# Refresh from existing Godot state
# --------------------------------------------------

func refresh_document(
	connector: Node,
	treatments: Node,
	teeth: Node
) -> void:
	_connector = connector
	_treatments = treatments
	_teeth = teeth

	_snapshot = _collect_document()
	_render_preview()


# --------------------------------------------------
# Collect existing data
# --------------------------------------------------

func _collect_document() -> Dictionary:
	if _connector == null or _treatments == null:
		return {}

	if not bool(_connector.case_ready):
		return {}

	if _treatments.evaluated_spans.is_empty():
		return {}

	var clinical_case: Dictionary = _connector.current_case

	var report: Dictionary = {
		"patient": str(_connector.patient_display_name),
		"encounter": _encounter_text(clinical_case),
		"measurements": [],
		"spans": []
	}

	# Only measurements actually present in the case.

	var measurements: Dictionary = clinical_case.get(
		"measurements", {}
	)

	if measurements.get("hba1c") != null:
		report["measurements"].append({
			"label": "HbA1c",
			"value": str(measurements["hba1c"]) + "%"
		})

	for item in _treatments.evaluated_spans:
		if not item is Dictionary:
			continue

		var evaluation: Dictionary = item.get(
			"evaluation", {}
		)
		var knowledge: Dictionary = evaluation.get(
			"knowledge", {}
		)
		var records: Array = knowledge.get(
			"treatments", []
		)

		var entries: Array = []

		# Include available alternatives, including
		# treatments with soft clinical cautions.
		# Excluded alternatives are not included.

		for outcome in evaluation.get("treatments", []):
			if not outcome is Dictionary:
				continue

			if str(outcome.get("status", "")) not in [
				"Available",
				"Caution"
			]:
				continue

			var treatment: Dictionary = outcome.get(
				"treatment", {}
			)
			var code := str(treatment.get("code", ""))

			for record in records:
				if not record is Dictionary:
					continue

				if str(
					record.get("treatment_code", "")
				) == code:
					entries.append(
						_document_entry(record, outcome)
					)
					break

		# No Intervention is included as an
		# informational alternative, not a
		# fabricated clinical evaluation result.

		for record in records:
			if not record is Dictionary:
				continue

			if (
				record.get("treatment_code") == null
				and record.get("guideline_id") == null
			):
				entries.append(
					_document_entry(record, {})
				)
				break

		if entries.is_empty():
			continue

		var missing: PackedStringArray = []

		for tooth in item.get("span", []):
			var fdi := str(tooth)
			var tooth_name := ""

			if _teeth != null:
				tooth_name = str(
					_teeth.get_tooth_name(fdi)
				).capitalize()

			missing.append(
				(
					tooth_name
					if not tooth_name.is_empty()
					else "Tooth"
				)
				+ " (FDI "
				+ fdi
				+ ")"
			)

		report["spans"].append({
			"missing": ", ".join(missing),
			"entries": entries
		})

	if report["spans"].is_empty():
		return {}

	return report


# --------------------------------------------------
# Encounter information
# --------------------------------------------------

func _encounter_text(
	clinical_case: Dictionary
) -> String:
	var encounter_id := str(
		clinical_case.get("encounter", "")
	)

	for item in _connector.encounters:
		if not item is Dictionary:
			continue

		if str(item.get("id", "")) != encounter_id:
			continue

		var period: Dictionary = item.get("period", {})
		var start := str(period.get("start", ""))

		if start.length() >= 10:
			return start.substr(0, 10)

	return encounter_id


# --------------------------------------------------
# Treatment records
# --------------------------------------------------

func _document_entry(
	record: Dictionary,
	outcome: Dictionary
) -> Dictionary:
	var attributes: Array = []

	for attribute in record.get("attributes", []):
		if attribute is Dictionary:
			attributes.append({
				"label": _plain(attribute.get("label")),
				"value": _plain(
					attribute.get("display_value")
				)
			})

	var procedures: Array = []
	var maintenance: Array = []

	var image_path := ""
	var image_credit := ""

	for procedure in record.get("procedures", []):
		if not procedure is Dictionary:
			continue

		var lines: Array = []

		for step in procedure.get("steps", []):
			if not step is Dictionary:
				continue

			var title := _plain(step.get("title"))
			var explanation := _plain(
				step.get("explanation")
			)

			if (
				not title.is_empty()
				or not explanation.is_empty()
			):
				lines.append({
					"title": title,
					"description": explanation
				})

			# One existing representative illustration,
			# rather than all procedure-step images.

			if str(
				procedure.get("procedure_type", "")
			) == "treatment":
				var media_id := str(
					_treatments.get_step_media_id(
						str(step.get("step_id", ""))
					)
				)

				var media: Dictionary = (
					_connector.media_catalogue.get(
						media_id, {}
					)
				)

				var path := str(
					media.get("file_path", "")
				)

				if not path.is_empty():
					if not path.begins_with("res://"):
						path = (
							"res://"
							+ path.trim_prefix("/")
						)

					if ResourceLoader.exists(path):
						image_path = path

						var credit_parts: PackedStringArray = []

						for key in [
							"creator",
							"license_name"
						]:
							var value := _plain(media.get(key))

							if not value.is_empty():
								credit_parts.append(value)

						image_credit = " · ".join(
							credit_parts
						)

		var block := {
			"explanation": _plain(
				procedure.get("explanation")
			),
			"steps": lines
		}

		if str(
			procedure.get("procedure_type", "")
		) == "treatment":
			procedures.append(block)

		elif str(
			procedure.get("procedure_type", "")
		) == "maintenance":
			maintenance.append(block)

	return {
		"name": _plain(record.get("name")),
		"summary": _plain(record.get("summary")),
		"explanation": _plain(record.get("explanation")),
		"attributes": attributes,
		"procedures": procedures,
		"maintenance": maintenance,
		"image": image_path,
		"image_credit": image_credit
	}


# --------------------------------------------------
# Godot preview
# --------------------------------------------------

func _render_preview() -> void:
	for child in _content.get_children():
		_content.remove_child(child)
		child.queue_free()

	_print_button.disabled = _snapshot.is_empty()

	if _snapshot.is_empty():
		_message.text = (
			"Evaluate a clinical case "
			+ "to prepare the summary."
		)
		return

	_message.text = "Patient-facing document preview"

	# Section 1: Patient and clinical information.

	_heading(
		_content,
		"1. Patient and clinical information",
		18
	)

	_line(
		_content,
		"Patient: "
		+ _nonempty(str(_snapshot["patient"]))
	)

	if not str(_snapshot["encounter"]).is_empty():
		_line(
			_content,
			"Encounter: "
			+ str(_snapshot["encounter"])
		)

	for span in _snapshot["spans"]:
		_line(
			_content,
			"Missing teeth evaluated: "
			+ str(span["missing"])
		)

	for measure in _snapshot["measurements"]:
		_line(
			_content,
			str(measure["label"])
			+ ": "
			+ str(measure["value"])
		)

	# Section 2: Treatment comparison.

	_heading(
		_content,
		"2. Treatment comparison",
		18
	)

	for span in _snapshot["spans"]:
		_heading(
			_content,
			str(span["missing"]),
			14
		)
		_preview_table(span["entries"])

	# Section 3: Treatment details.

	_heading(
		_content,
		"3. Treatment information",
		18
	)

	for span in _snapshot["spans"]:
		_heading(
			_content,
			str(span["missing"]),
			14
		)

		for entry in span["entries"]:
			var card := PanelContainer.new()
			var style := StyleBoxFlat.new()

			style.bg_color = PANEL
			style.border_color = BORDER
			style.set_border_width_all(1)
			style.set_content_margin_all(12)

			card.add_theme_stylebox_override(
				"panel", style
			)
			_content.add_child(card)

			var column := VBoxContainer.new()
			column.add_theme_constant_override(
				"separation", 7
			)
			card.add_child(column)

			_heading(column, str(entry["name"]), 16)
			_line_if(column, str(entry["summary"]))
			_line_if(column, str(entry["explanation"]))

			_preview_image(
				column,
				str(entry["image"])
			)

			_line_if(
				column,
				str(entry["image_credit"])
			)

			for attribute in entry["attributes"]:
				_line(
					column,
					str(attribute["label"])
					+ ": "
					+ str(attribute["value"])
				)

			_preview_steps(
				column,
				"Procedure information",
				entry["procedures"]
			)

			_preview_steps(
				column,
				"Maintenance information",
				entry["maintenance"]
			)


# --------------------------------------------------
# Preview comparison
# --------------------------------------------------

func _preview_table(entries: Array) -> void:
	var horizontal := ScrollContainer.new()
	horizontal.custom_minimum_size.y = 340
	horizontal.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)
	horizontal.vertical_scroll_mode = (
		ScrollContainer.SCROLL_MODE_AUTO
	)
	_content.add_child(horizontal)

	var matrix := GridContainer.new()
	matrix.columns = entries.size() + 1
	matrix.add_theme_constant_override(
		"h_separation", 4
	)
	matrix.add_theme_constant_override(
		"v_separation", 4
	)
	horizontal.add_child(matrix)

	_table_cell(matrix, "Characteristic", true)

	for entry in entries:
		_table_cell(
			matrix,
			str(entry["name"]),
			true
		)

	for label in _attribute_labels(entries):
		_table_cell(matrix, label, true)

		for entry in entries:
			_table_cell(
				matrix,
				_attribute_value(entry, label),
				false
			)


func _table_cell(
	matrix: GridContainer,
	value: String,
	header: bool
) -> void:
	var card := PanelContainer.new()
	card.custom_minimum_size.x = 160

	var style := StyleBoxFlat.new()
	style.bg_color = BLUE if header else PANEL
	style.set_content_margin_all(8)

	card.add_theme_stylebox_override("panel", style)
	matrix.add_child(card)
	_line(card, value)


# --------------------------------------------------
# Preview media and brochures
# --------------------------------------------------

func _preview_image(
	parent: VBoxContainer,
	path: String
) -> void:
	if path.is_empty():
		return

	var resource := load(path)

	if not resource is Texture2D:
		return

	var picture := TextureRect.new()
	picture.texture = resource as Texture2D
	picture.custom_minimum_size.y = 155
	picture.expand_mode = (
		TextureRect.EXPAND_IGNORE_SIZE
	)
	picture.stretch_mode = (
		TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	)
	parent.add_child(picture)


func _preview_steps(
	parent: VBoxContainer,
	heading: String,
	blocks: Array
) -> void:
	if blocks.is_empty():
		return

	_heading(parent, heading, 13)

	for block in blocks:
		_line_if(
			parent,
			str(block["explanation"])
		)

		for step in block["steps"]:
			_line(
				parent,
				"• "
				+ str(step["title"])
				+ ". "
				+ str(step["description"])
			)


# --------------------------------------------------
# Preview text controls
# --------------------------------------------------

func _heading(
	parent: Node,
	value: String,
	font_size: int
) -> void:
	var label := Label.new()
	label.text = value
	label.autowrap_mode = (
		TextServer.AUTOWRAP_WORD_SMART
	)
	label.add_theme_font_size_override(
		"font_size", font_size
	)
	label.add_theme_color_override(
		"font_color", INK
	)
	parent.add_child(label)


func _line(
	parent: Node,
	value: String
) -> void:
	var label := Label.new()
	label.text = value
	label.autowrap_mode = (
		TextServer.AUTOWRAP_WORD_SMART
	)
	label.add_theme_font_size_override(
		"font_size", 12
	)
	label.add_theme_color_override(
		"font_color", MUTED
	)
	parent.add_child(label)


func _line_if(
	parent: Node,
	value: String
) -> void:
	if not value.is_empty():
		_line(parent, value)


func _attribute_labels(entries: Array) -> Array:
	var labels: Array = []

	for entry in entries:
		for attribute in entry["attributes"]:
			var label := str(attribute["label"])

			if (
				not label.is_empty()
				and not labels.has(label)
			):
				labels.append(label)

	return labels


func _attribute_value(
	entry: Dictionary,
	label: String
) -> String:
	for attribute in entry["attributes"]:
		if str(attribute["label"]) == label:
			return _nonempty(
				str(attribute["value"])
			)

	return "Not provided"


# --------------------------------------------------
# Print / Save as PDF
# --------------------------------------------------

func _print_document() -> void:
	if _snapshot.is_empty():
		return

	var output := "user://after_visit_summary.html"

	var file := FileAccess.open(
		output,
		FileAccess.WRITE
	)

	if file == null:
		_message.text = (
			"Could not create the printable document."
		)
		push_error(
			"AVS file error: "
			+ str(FileAccess.get_open_error())
		)
		return

	file.store_string(_build_html())
	file.close()

	var result := OS.shell_open(
		ProjectSettings.globalize_path(output)
	)

	if result != OK:
		_message.text = (
			"Document saved, but could not be opened."
		)
		push_error(
			"AVS open error: " + str(result)
		)


# --------------------------------------------------
# HTML document
# --------------------------------------------------

func _build_html() -> String:
	var parts := PackedStringArray()

	parts.append("""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>After Visit Summary</title>

<style>

@page {
	size: A4 landscape;
	margin: 19mm 13mm 17mm 13mm;

	@top-left {
		content: "__AVS_PATIENT__";
		font: 9pt Arial, sans-serif;
		color: #42566d;
	}

	@top-right {
		content: "__AVS_DATE__";
		font: 9pt Arial, sans-serif;
		color: #42566d;
	}

	@bottom-left {
		content: "After Visit Summary";
		font: 8pt Arial, sans-serif;
		color: #536477;
	}

	@bottom-right {
		content: "Page " counter(page) " of " counter(pages);
		font: 8pt Arial, sans-serif;
		color: #536477;
	}
}

* {
	box-sizing: border-box;
}

body {
	font: 11pt Arial, sans-serif;
	color: #1b2939;
	margin: 0;
	line-height: 1.42;
}

header {
	border-bottom: 3px solid #294d79;
	padding: 0 0 12px;
	margin: 0 0 18px;
}

h1 {
	font-size: 22pt;
	margin: 0;
}

h2 {
	font-size: 16pt;
	border-bottom: 1px solid #b8c8da;
	padding-bottom: 6px;
	margin: 18px 0 12px;
}

h3 {
	font-size: 13pt;
	margin: 0 0 10px;
}

h4 {
	font-size: 11pt;
	margin: 13px 0 6px;
}

p {
	margin: 6px 0 10px;
}

.section {
	break-before: page;
}

.entry {
	border: 1px solid #bccbda;
	padding: 12px 15px;
	margin: 14px 0;
	break-inside: avoid-page;
}

.entry::after {
	content: "";
	display: block;
	clear: both;
}

/* One representative image on the right. */

.entry figure.treatment-image {
	float: right;
	width: 36%;
	margin: 0 0 10px 18px;
	text-align: center;
}

.entry figure.treatment-image img {
	display: block;
	width: 100%;
	max-height: 55mm;
	object-fit: contain;
}

.caption {
	font-size: 8pt;
	color: #536477;
	text-align: center;
	margin-top: 5px;
}

table {
	border-collapse: collapse;
	width: 100%;
	table-layout: fixed;
	font-size: 9pt;
}

th, td {
	border: 1px solid #b8c8da;
	padding: 9px;
	vertical-align: top;
	overflow-wrap: break-word;
}

th {
	background: #e1ecf8;
	text-align: left;
}

ul, ol {
	margin: 5px 0 12px;
	padding-left: 20px;
}

li {
	margin: 4px 0;
}

button {
	background: #294d79;
	color: white;
	border: 0;
	border-radius: 5px;
	padding: 10px 16px;
	cursor: pointer;
	margin: 0 0 15px;
}

@media print {
	button {
		display: none;
	}

	.entry {
		break-inside: auto;
	}

	h2, h3, h4 {
		break-after: avoid;
	}

	.entry figure.treatment-image {
		break-inside: avoid;
	}
}

</style>
</head>
<body>

<button onclick="window.print()">
	Print / Save as PDF
</button>

<header>
	<h1>After Visit Summary</h1>
	<div>
		Treatment information for your dental health
	</div>
</header>
""")

	# --------------------------------------------------
	# Section 1: Patient and clinical information
	# --------------------------------------------------

	parts.append(
		"<h2>1. Patient and clinical information</h2>"
	)

	parts.append(
		"<p><b>Patient:</b> "
		+ _escape(
			_nonempty(str(_snapshot["patient"]))
		)
		+ "</p>"
	)

	if not str(_snapshot["encounter"]).is_empty():
		parts.append(
			"<p><b>Encounter:</b> "
			+ _escape(str(_snapshot["encounter"]))
			+ "</p>"
		)

	for span in _snapshot["spans"]:
		parts.append(
			"<p><b>Missing teeth evaluated:</b> "
			+ _escape(str(span["missing"]))
			+ "</p>"
		)

	for measure in _snapshot["measurements"]:
		parts.append(
			"<p><b>"
			+ _escape(str(measure["label"]))
			+ ":</b> "
			+ _escape(str(measure["value"]))
			+ "</p>"
		)

	# --------------------------------------------------
	# Section 2: Treatment comparison
	# --------------------------------------------------

	parts.append(
		"<section class='section'>"
		+ "<h2>2. Treatment comparison</h2>"
	)

	for span in _snapshot["spans"]:
		var entries: Array = span["entries"]

		parts.append(
			"<h3>"
			+ _escape(str(span["missing"]))
			+ "</h3>"
		)

		parts.append(
			"<table><thead><tr>"
			+ "<th>Characteristic</th>"
		)

		for entry in entries:
			parts.append(
				"<th>"
				+ _escape(str(entry["name"]))
				+ "</th>"
			)

		parts.append("</tr></thead><tbody>")

		for label in _attribute_labels(entries):
			parts.append(
				"<tr><th>"
				+ _escape(label)
				+ "</th>"
			)

			for entry in entries:
				parts.append(
					"<td>"
					+ _escape(
						_attribute_value(entry, label)
					)
					+ "</td>"
				)

			parts.append("</tr>")

		parts.append("</tbody></table>")

	parts.append("</section>")

	# --------------------------------------------------
	# Section 3: Individual treatment information
	# --------------------------------------------------

	parts.append(
		"<section class='section'>"
		+ "<h2>3. Treatment information</h2>"
	)

	for span in _snapshot["spans"]:
		parts.append(
			"<h3>"
			+ _escape(str(span["missing"]))
			+ "</h3>"
		)

		for entry in span["entries"]:
			parts.append(
				"<article class='entry'>"
				+ "<h3>"
				+ _escape(str(entry["name"]))
				+ "</h3>"
			)

			# Place image before the paragraphs so
			# existing text flows beside it.

			var image_tag := _image_html(
				str(entry["image"]),
				str(entry["image_credit"])
			)

			if not image_tag.is_empty():
				parts.append(image_tag)

			for field in [
				"summary",
				"explanation"
			]:
				if not str(entry[field]).is_empty():
					parts.append(
						"<p>"
						+ _escape(str(entry[field]))
						+ "</p>"
					)

			if not entry["attributes"].is_empty():
				parts.append("<ul>")

				for attribute in entry["attributes"]:
					parts.append(
						"<li><b>"
						+ _escape(str(attribute["label"]))
						+ ":</b> "
						+ _escape(str(attribute["value"]))
						+ "</li>"
					)

				parts.append("</ul>")

			parts.append(
				_blocks_html(
					"Procedure information",
					entry["procedures"]
				)
			)

			parts.append(
				_blocks_html(
					"Maintenance information",
					entry["maintenance"]
				)
			)

			parts.append("</article>")

	parts.append("</section></body></html>")

	# --------------------------------------------------
	# Custom print header / footer
	# --------------------------------------------------

	var html := "\n".join(parts)

	html = html.replace(
		"__AVS_PATIENT__",
		_css_content_text(
			str(_snapshot["patient"])
		)
	)

	html = html.replace(
		"__AVS_DATE__",
		_css_content_text(
			Time.get_date_string_from_system()
		)
	)

	return html


# --------------------------------------------------
# Procedure and maintenance text
# --------------------------------------------------

func _blocks_html(
	title: String,
	blocks: Array
) -> String:
	if blocks.is_empty():
		return ""

	var pieces := PackedStringArray()

	pieces.append(
		"<h4>"
		+ _escape(title)
		+ "</h4>"
	)

	for block in blocks:
		if not str(block["explanation"]).is_empty():
			pieces.append(
				"<p>"
				+ _escape(str(block["explanation"]))
				+ "</p>"
			)

		if not block["steps"].is_empty():
			pieces.append("<ol>")

			for step in block["steps"]:
				pieces.append(
					"<li><b>"
					+ _escape(str(step["title"]))
					+ "</b> "
					+ _escape(str(step["description"]))
					+ "</li>"
				)

			pieces.append("</ol>")

	return "\n".join(pieces)


# --------------------------------------------------
# Representative image for print
# --------------------------------------------------

func _image_html(
	path: String,
	credit: String
) -> String:
	if path.is_empty():
		return ""

	var resource := load(path)

	if not resource is Texture2D:
		return ""

	var texture := resource as Texture2D
	var picture: Image = texture.get_image()

	if picture == null:
		return ""

	if picture.is_compressed():
		if picture.decompress() != OK:
			return ""

	var bytes := picture.save_png_to_buffer()

	if bytes.is_empty():
		return ""

	var result := (
		"<figure class='treatment-image'>"
		+ "<img alt='Treatment illustration' "
		+ "src='data:image/png;base64,"
		+ Marshalls.raw_to_base64(bytes)
		+ "'>"
	)

	if not credit.is_empty():
		result += (
			"<figcaption class='caption'>"
			+ _escape(credit)
			+ "</figcaption>"
		)

	result += "</figure>"

	return result


# --------------------------------------------------
# Text and escaping helpers
# --------------------------------------------------

func _plain(value: Variant) -> String:
	if value == null:
		return ""

	return str(value).strip_edges()


func _nonempty(value: String) -> String:
	return (
		value
		if not value.is_empty()
		else "Not provided"
	)


func _escape(value: String) -> String:
	return (
		value
		.replace("&", "&amp;")
		.replace("<", "&lt;")
		.replace(">", "&gt;")
		.replace('"', "&quot;")
		.replace("'", "&#39;")
	)


func _css_content_text(value: String) -> String:
	return (
		value
		.replace("\\", "\\\\")
		.replace('"', '\\"')
		.replace("\n", " ")
		.replace("\r", " ")
	)
