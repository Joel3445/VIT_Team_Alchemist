extends CanvasLayer

@onready var dialogue_box = $DialogueBox
@onready var dialogue_text = $DialogueBox/MarginContainer/DialogueText

var dialogue_lines = []
var current_line = 0

func _ready():
	hide_dialogue()

func start_dialogue(lines: Array):
	dialogue_lines = lines
	current_line = 0
	show_dialogue()
	show_line()

func show_line():
	if current_line < dialogue_lines.size():
		dialogue_text.text = dialogue_lines[current_line]
	else:
		hide_dialogue()

func next_line():
	current_line += 1
	show_line()

func show_dialogue():
	dialogue_box.visible = true

func hide_dialogue():
	dialogue_box.visible = false
	
func _input(event):
	if dialogue_box.visible and event.is_action_pressed("ui_accept"):
		next_line()
