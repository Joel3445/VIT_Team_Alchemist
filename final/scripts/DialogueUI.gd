extends CanvasLayer

# Viewport is 1100x619 (from screenshot top-right corner)
# Dialog box png is 1021x244 — scale it to fit safely inside viewport
const BOX_X     = 550    # horizontal center
const BOX_Y     = 560    # vertical center of box
const BOX_SCALE = 0.98   # keeps it within 1100px wide
const FONT_SIZE = 18

var _box:  Sprite2D
var _text: Label

func _ready():
	_box          = Sprite2D.new()
	_box.texture  = load("res://assets/dialog_box.png")
	_box.position = Vector2(BOX_X, BOX_Y)
	# 1021 * 0.98 = ~1000px wide — fits in 1100px viewport
	# height: 244 * 0.98 * 0.58 = ~139px
	_box.scale    = Vector2(BOX_SCALE, BOX_SCALE * 0.58)
	add_child(_box)

	_text          = Label.new()
	_text.size     = Vector2(900, 110)
	_text.position = Vector2(BOX_X - 450, BOX_Y - 52)
	_text.horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
	_text.vertical_alignment   = VERTICAL_ALIGNMENT_CENTER
	_text.autowrap_mode        = TextServer.AUTOWRAP_WORD_SMART
	_text.add_theme_font_size_override("font_size", FONT_SIZE)
	_text.add_theme_color_override("font_color", Color(0, 0, 0, 1))
	add_child(_text)

	hide_text()

func show_text(message: String):
	_box.visible  = true
	_text.visible = true
	_text.text    = message

func hide_text():
	_box.visible  = false
	_text.visible = false

func show_dialogue(message: String):
	show_text(message)
