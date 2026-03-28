extends Node

@onready var loader   = $GLAMLoader
@onready var registry = $RegisterManager
@onready var runner   = $ExperimentRunner
@onready var ui       = $DialogueUI
var mascot_animator: Node = null

var current_dsl:    Dictionary = {}
var dialogue_lines: Array      = []
var dialogue_index: int        = 0
var is_talking:     bool       = false
var held_item_id:   String     = ""
var held_item_node: Node       = null

const WRONG_ITEM_LINES = {
	"salt":        "Salt?! Put that back! Are we making soup? Pick up the VINEGAR!",
	"sugar":       "Sugar! Absolutely not! We need VINEGAR for this experiment!",
	"baking_soda": "Not that — we are only using VINEGAR today. Pay attention!",
	"water":       "That is water, not vinegar! Look at the labels carefully!",
	"flask":       "We are not using the flask today. Find the VINEGAR on the shelf!",
	"test_tube":   "Wrong equipment! We need VINEGAR from the shelf, not that!",
	"burner":      "No no no! Do not touch the burner yet! Pick up the VINEGAR first!",
	"default":     "That is NOT what I asked for! Pick up the VINEGAR from the shelf!",
}

func _ready() -> void:
	runner.step_changed.connect(_on_step_changed)
	runner.experiment_complete.connect(_on_experiment_complete)
	await get_tree().process_frame
	var mascot_node = get_node_or_null("/root/Main/Mascot")
	if mascot_node:
		mascot_animator = mascot_node
	start_quest("glam_quest")

func start_quest(quest_id: String) -> void:
	var dsl = loader.load_dsl(quest_id)
	if dsl.is_empty():
		return
	current_dsl = dsl
	registry.load_registers(dsl)
	runner.load_experiment(dsl, registry)
	_build_dialogue_lines()
	# Show opening instruction immediately
	ui.show_text("Press E to talk to the Professor!")
	print("GLAM: Quest loaded")

func _build_dialogue_lines() -> void:
	dialogue_lines.clear()
	var dialogue = current_dsl.get("dialogue", {})
	var main     = dialogue.get("MAIN", {})
	var steps    = current_dsl.get("experiment", {}).get("steps", [])
	var start_line = main.get("start", "")
	if start_line != "":
		dialogue_lines.append(start_line)
	for step in steps:
		var desc = step.get("description", "")
		if desc != "":
			dialogue_lines.append(desc)
	var end_line = main.get("end", "")
	if end_line != "":
		dialogue_lines.append(end_line)
	dialogue_index = 0
	print("GLAM: ", dialogue_lines.size(), " dialogue lines")

func on_item_picked_up(item_id: String, _action_id: String, item_node: Node) -> void:
	held_item_id   = item_id
	held_item_node = item_node
	if mascot_animator:
		mascot_animator.react_correct()
	var desc = runner.current_step.get("description", "Good! Now pour it into the beaker.")
	ui.show_text("Good choice! " + desc)
	runner.try_advance("collect_item", registry)

func show_wrong_item_dialogue(item_id: String) -> void:
	var line = WRONG_ITEM_LINES.get(item_id, WRONG_ITEM_LINES["default"])
	ui.show_text(line)
	await get_tree().create_timer(3.0).timeout
	# Only hide if nothing else replaced the text
	ui.hide_text()

func on_pour_complete(liquid: String) -> void:
	print("GLAM: Pour complete — ", liquid)
	if held_item_node and held_item_node.has_method("release_cursor"):
		held_item_node.release_cursor()
	held_item_id   = ""
	held_item_node = null
	runner.try_advance("mix_items", registry)
	if mascot_animator:
		mascot_animator.react_correct()
	var desc = runner.current_step.get("description", "Now click the beaker to observe!")
	ui.show_text(desc)

func on_beaker_clicked() -> void:
	var step_id = runner.current_step.get("state_id", "")

	# If player has item held — pour it
	if held_item_id != "":
		var beaker = get_node_or_null("/root/Main/Beaker")
		if beaker:
			var anim = beaker.get_node_or_null("BeakerAnimator")
			if anim:
				anim.pour(held_item_id)
		return

	# If we are on observe step — advance
	if step_id == "STEP_OBSERVE":
		runner.try_advance("observe_reaction", registry)
		return

	# Otherwise — tell player what to do
	var hint = runner.current_step.get("description", "Follow the professor's instructions!")
	ui.show_text(hint)
	if mascot_animator:
		mascot_animator.react_wrong()
	await get_tree().create_timer(2.5).timeout
	ui.hide_text()

func _input(event: InputEvent) -> void:
	if not event is InputEventKey or not event.pressed:
		return
	match event.keycode:
		KEY_E:
			if dialogue_lines.is_empty():
				return
			if not is_talking:
				is_talking     = true
				dialogue_index = 0
				ui.show_text(dialogue_lines[dialogue_index])
				if mascot_animator:
					mascot_animator.react_correct()
				return
			dialogue_index += 1
			if dialogue_index >= dialogue_lines.size():
				ui.hide_text()
				is_talking     = false
				dialogue_index = 0
			else:
				ui.show_text(dialogue_lines[dialogue_index])
			runner.try_advance("talk", registry)
		KEY_ESCAPE:
			ui.hide_text()
			is_talking = false
			if held_item_node and held_item_node.has_method("release_cursor"):
				held_item_node.release_cursor()
			held_item_id   = ""
			held_item_node = null

func _on_step_changed(step: Dictionary) -> void:
	print("GLAM step -> ", step.get("state_id",""), ": ", step.get("description",""))
	# Show step description automatically when step changes
	if not is_talking:
		ui.show_text(step.get("description", ""))

func _on_experiment_complete() -> void:
	print("GLAM: Quest complete!")
	if mascot_animator:
		mascot_animator.react_complete()
	var end_line = current_dsl.get("dialogue",{}).get("MAIN",{}).get("end","Well done!")
	ui.show_text(end_line)
