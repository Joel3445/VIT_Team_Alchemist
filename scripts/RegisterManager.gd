extends Node

var assets:     Dictionary = {}
var actions:    Dictionary = {}
var states:     Dictionary = {}
var effects:    Dictionary = {}
var conditions: Dictionary = {}
var reactions:  Dictionary = {}

func load_registers(dsl: Dictionary) -> void:
	var reg = dsl.get("registers", {})

	for a in reg.get("assets", []):
		assets[a["id"]] = a

	for a in reg.get("actions", []):
		actions[a["id"]] = a

	for s in reg.get("states", []):
		states[s["id"]] = {"asset": s["asset"], "value": s["value"]}

	for e in reg.get("effects", []):
		effects[e["id"]] = {"changes": e["changes"], "to": e["to"]}

	for c in reg.get("conditions", []):
		conditions[c["id"]] = {"check": c["check"], "equals": c["equals"]}

	for r in reg.get("reactions", []):
		reactions[r["id"]] = r

	print("GLAM Registers loaded — assets: ", assets.size(),
		  "  actions: ", actions.size(),
		  "  reactions: ", reactions.size())

func get_asset_label(asset_id: String) -> String:
	return assets.get(asset_id, {}).get("label", asset_id)

func check_condition(cond_id: String, world_state: Dictionary) -> bool:
	var cond = conditions.get(cond_id, {})
	if cond.is_empty():
		return true  # no condition = always pass
	var state_id = cond["check"]
	var expected = cond["equals"]
	return str(world_state.get(state_id, "")) == expected

func apply_effect(effect_id: String, world_state: Dictionary) -> void:
	var eff = effects.get(effect_id, {})
	if eff.is_empty():
		return
	world_state[eff["changes"]] = eff["to"]
	print("GLAM Effect: ", eff["changes"], " → ", eff["to"])
