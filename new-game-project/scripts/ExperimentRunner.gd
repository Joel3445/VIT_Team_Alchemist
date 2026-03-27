extends Node

signal step_changed(step: Dictionary)
signal experiment_complete

var steps:        Array      = []
var step_map:     Dictionary = {}  # state_id → step dict
var current_step: Dictionary = {}
var world_state:  Dictionary = {}  # live state of the world

func load_experiment(dsl: Dictionary, register_mgr: Node) -> void:
	var exp = dsl.get("experiment", {})
	steps = exp.get("steps", [])

	step_map.clear()
	for s in steps:
		step_map[s["state_id"]] = s

	var start_id = exp.get("start", "")
	if step_map.has(start_id):
		current_step = step_map[start_id]
		print("GLAM Experiment started at: ", start_id)
		emit_signal("step_changed", current_step)
	else:
		push_error("GLAM: start step not found → " + start_id)

func try_advance(action_id: String, register_mgr: Node) -> void:
	if current_step.is_empty():
		return

	var wire = current_step.get("wire", {})

	# Check the action matches
	if wire.get("on", "") != action_id:
		print("GLAM: action '", action_id, "' doesn't match wire '", wire.get("on",""), "'")
		return

	# Check condition
	var cond_id = wire.get("condition", "")
	if cond_id != "" and not register_mgr.check_condition(cond_id, world_state):
		print("GLAM: condition '", cond_id, "' not met yet")
		return

	# Advance
	var next_id = wire.get("next", "END")
	if next_id == "END":
		print("GLAM: Experiment complete!")
		current_step = {}
		emit_signal("experiment_complete")
		return

	if step_map.has(next_id):
		current_step = step_map[next_id]
		print("GLAM: Step → ", next_id)
		emit_signal("step_changed", current_step)
	else:
		push_error("GLAM: next step not found → " + next_id)

func get_current_description() -> String:
	return current_step.get("description", "")
