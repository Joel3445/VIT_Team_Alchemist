extends Node2D

@onready var player = $VideoStreamPlayer

func _ready():
	player.finished.connect(_on_finished)
	player.visible = false

func pour(liquid: String):
	player.set_meta("liquid", liquid)
	player.visible = true
	player.play()

# keep old method names working too
func pour_vinegar():
	pour("vinegar")

func fill_water():
	pour("water")

func _on_finished():
	player.visible = false
	var liquid = player.get_meta("liquid", "")
	var glam   = get_node("/root/Main/GLAMSystem")
	glam.on_pour_complete(liquid)
