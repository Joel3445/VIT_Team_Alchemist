extends Sprite2D

var current_item: String = ""

func _process(delta):
	global_position = get_viewport().get_mouse_position()

func set_item(item_id: String, texture: Texture2D):
	current_item = item_id
	self.texture = texture
	visible = true

func clear_item():
	current_item = ""
	visible = false
