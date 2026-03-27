extends Node

@onready var loader   = $GLAMLoader
@onready var registry = $RegisterManager
@onready var runner   = $ExperimentRunner

func _ready() -> void:
	runner.step_changed.connect(_on_step_changed)
	runner.experiment_complete.connect(_on_experiment_complete)

	# ← change this to your quest id (filename without .json)
	start_quest("test1")

func start_quest(quest_id: String) -> void:
	var dsl = loader.load_dsl(quest_id)
	if dsl.is_empty():
		return
	registry.load_registers(dsl)
	runner.load_experiment(dsl, registry)

# Call this from your player/NPC scripts when something happens
# e.g. GLAMSystem.do_action("COLLECT_WATER")
func do_action(action_id: String) -> void:
	runner.try_advance(action_id, registry)

func set_state(state_id: String, value: String) -> void:
	runner.world_state[state_id] = value

func _on_step_changed(step: Dictionary) -> void:
	print("=== Step: ", step.get("state_id",""), " ===")
	print("    ", step.get("description",""))
	# Hook your UI/dialogue here later

func _on_experiment_complete() -> void:
	print("Quest complete!")
	# Trigger your end screen / reward here
