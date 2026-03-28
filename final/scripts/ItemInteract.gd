extends Area2D

@export var item_id:      String    = ""
@export var item_texture: Texture2D = null
@export var is_correct:   bool      = true

var _collected: bool = false

func _ready():
	input_pickable = true

func _input_event(_viewport, event, _shape_idx):
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		_on_clicked()

func _on_clicked():
	var glam = get_node_or_null("/root/Main/GLAMSystem")
	if glam == null:
		print("GLAMSystem not found!")
		return
	if not is_correct:
		glam.show_wrong_item_dialogue(item_id)
		return
	print("Item clicked: ", item_id)
	glam.on_item_picked_up(item_id, "COLLECT_ITEM", self)

func release_cursor():
	DisplayServer.mouse_set_mode(DisplayServer.MOUSE_MODE_VISIBLE)
	_collected = false
