extends Node2D

# Mascot base sprite is 128x128, displaextends Node2D

@onready var eyes  = get_node_or_null("Eyes")
@onready var mouth = get_node_or_null("Mouth")

var _tex_eye_open:    Texture2D
var _tex_mouth_small: Texture2D
var _tex_mouth_wide:  Texture2D
var _mouth_timer: float = 0.0
var _mouth_open:  bool  = false
const MOUTH_CYCLE = 0.4

enum State { IDLE, CORRECT, WRONG, COMPLETE }
var _state:       State = State.IDLE
var _state_timer: float = 0.0
const REACTION_DURATION = 2.0

func _ready():
	_tex_eye_open    = load("res://assets/eyeopen.png")
	_tex_mouth_small = load("res://assets/mouthsmallopen.png")
	_tex_mouth_wide  = load("res://assets/mouthwideopen.png")
	if eyes:
		eyes.position  = Vector2(0, -22)
		eyes.z_index   = 2
	if mouth:
		mouth.position = Vector2(0, -8)
		mouth.z_index  = 2
	_set_state(State.IDLE)

func _process(delta: float):
	if eyes == null or mouth == null:
		return
	if _state in [State.CORRECT, State.WRONG, State.COMPLETE]:
		_state_timer -= delta
		if _state_timer <= 0.0:
			_set_state(State.IDLE)
		return
	_mouth_timer -= delta
	if _mouth_timer <= 0.0:
		_mouth_open   = not _mouth_open
		_mouth_timer  = MOUTH_CYCLE
		mouth.texture = _tex_mouth_wide if _mouth_open else _tex_mouth_small

func react_correct():
	_set_state(State.CORRECT)

func react_wrong():
	_set_state(State.WRONG)

func react_wrong_item():
	react_wrong()

func react_complete():
	_set_state(State.COMPLETE)

func _set_state(s: State):
	if eyes == null or mouth == null:
		return
	_state       = s
	_state_timer = REACTION_DURATION
	eyes.texture = _tex_eye_open
	match s:
		State.IDLE:
			eyes.modulate  = Color(1, 1, 1, 1)
			mouth.texture  = _tex_mouth_small
			mouth.modulate = Color(1, 1, 1, 1)
			_mouth_timer   = MOUTH_CYCLE
		State.WRONG:
			eyes.modulate  = Color(1.0, 0.3, 0.3, 1)
			mouth.texture  = _tex_mouth_wide
			mouth.modulate = Color(1, 1, 1, 1)
		State.CORRECT:
			eyes.modulate  = Color(0.3, 1.0, 0.4, 1)
			mouth.texture  = _tex_mouth_wide
			mouth.modulate = Color(1, 1, 1, 1)
		State.COMPLETE:
			eyes.modulate  = Color(1.0, 0.85, 0.2, 1)
			mouth.texture  = _tex_mouth_wide
			mouth.modulate = Color(1.0, 0.85, 0.2, 1)
