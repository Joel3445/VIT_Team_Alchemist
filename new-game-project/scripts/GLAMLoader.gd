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
	print("GLAM: Loaded → ", quest_id)
	return json.get_data()

func list_quests() -> Array:
	var quests = []
	var dir = DirAccess.open("res://data/quests/")
	if dir == null:
		return quests
	dir.list_dir_begin()
	var file = dir.get_next()
	while file != "":
		if file.ends_with(".json"):
			quests.append(file.replace(".json", ""))
		file = dir.get_next()
	return quests
