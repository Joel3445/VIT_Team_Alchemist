extends Node

func load_dsl(quest_id: String) -> Dictionary:
	var path = "res://data/quests/" + quest_id + ".json"
	var file = FileAccess.open(path, FileAccess.READ)
	if file == null:
		push_error("GLAM: Cannot open " + path)
		return {}
	var text = file.get_as_text()
	file.close()
	var json = JSON.new()
	if json.parse(text) != OK:
		push_error("GLAM: Invalid JSON in " + quest_id)
		return {}
	return json.get_data()
