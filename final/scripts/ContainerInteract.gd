extends Area2D

func _ready():
	input_pickable = true

func _input_event(_viewport, event, _shape_idx):
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed:
		var glam = get_node("/root/Main/GLAMSystem")
		glam.on_beaker_clicked()
