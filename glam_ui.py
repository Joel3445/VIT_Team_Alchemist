import sys
import json
import os
import re
import shutil
import zipfile
import requests
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QLabel, QLineEdit, QFileDialog,
    QSplitter, QFrame, QStatusBar, QMessageBox, QScrollArea,
    QStackedWidget, QProgressBar, QSizePolicy
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QPropertyAnimation, QRect
from PyQt5.QtGui import QColor, QTextCharFormat, QSyntaxHighlighter, QFont, QPalette

# ── Config ────────────────────────────────────────────────────────────────────
OLLAMA_URL  = "http://localhost:11434/api/generate"
MODEL       = "mistral"
DEFAULT_OUT = os.path.join(os.path.expanduser("~"), "godot_project", "data", "quests")

GDSCRIPTS = {
    "DialogueUI.gd": """\
extends CanvasLayer

@onready var box = $Box
@onready var text = $Box/Text

func _ready():
\tbox.visible = false

func show_text(message: String):
\tbox.visible = true
\ttext.text = message

func hide_text():
\tbox.visible = false
""",
    "ExperimentRunner.gd": """\
extends Node

signal step_changed(step: Dictionary)
signal experiment_complete

var steps:        Array      = []
var step_map:     Dictionary = {}
var current_step: Dictionary = {}
var world_state:  Dictionary = {}

func load_experiment(dsl: Dictionary, register_mgr: Node) -> void:
\tvar exp = dsl.get("experiment", {})
\tsteps = exp.get("steps", [])
\tstep_map.clear()
\tfor s in steps:
\t\tstep_map[s["state_id"]] = s
\tvar start_id = exp.get("start", "")
\tif step_map.has(start_id):
\t\tcurrent_step = step_map[start_id]
\t\temit_signal("step_changed", current_step)
\telse:
\t\tpush_error("GLAM: start step not found -> " + start_id)

func try_advance(action_id: String, register_mgr: Node) -> void:
\tif current_step.is_empty():
\t\treturn
\tvar wire = current_step.get("wire", {})
\tif wire.get("on", "") != action_id:
\t\treturn
\tvar cond_id = wire.get("condition", "")
\tif cond_id != "" and not register_mgr.check_condition(cond_id, world_state):
\t\treturn
\tvar next_id = wire.get("next", "END")
\tif next_id == "END":
\t\tcurrent_step = {}
\t\temit_signal("experiment_complete")
\t\treturn
\tif step_map.has(next_id):
\t\tcurrent_step = step_map[next_id]
\t\temit_signal("step_changed", current_step)
\telse:
\t\tpush_error("GLAM: next step not found -> " + next_id)

func get_current_description() -> String:
\treturn current_step.get("description", "")
""",
    "GLAMLoader.gd": """\
extends Node

func load_dsl(quest_id: String) -> Dictionary:
\tvar path = "res://data/quests/" + quest_id + ".json"
\tvar file = FileAccess.open(path, FileAccess.READ)
\tif file == null:
\t\tpush_error("GLAM: Cannot open " + path)
\t\treturn {}
\tvar text = file.get_as_text()
\tfile.close()
\tvar json = JSON.new()
\tif json.parse(text) != OK:
\t\tpush_error("GLAM: Invalid JSON in " + quest_id)
\t\treturn {}
\treturn json.get_data()
""",
    "GLAMSystem.gd": """\
extends Node

@onready var loader   = $GLAMLoader
@onready var registry = $RegisterManager
@onready var runner   = $ExperimentRunner

var current_dsl: Dictionary = {}

func _ready() -> void:
\trunner.step_changed.connect(_on_step_changed)
\trunner.experiment_complete.connect(_on_experiment_complete)
\tstart_quest("dialoguetest")

func start_quest(quest_id: String) -> void:
\tvar dsl = loader.load_dsl(quest_id)
\tif dsl.is_empty():
\t\treturn
\tcurrent_dsl = dsl
\tregistry.load_registers(dsl)
\trunner.load_experiment(dsl, registry)

func _on_step_changed(step: Dictionary) -> void:
\tprint("Step: ", step.get("state_id",""), " - ", step.get("description",""))

func _on_experiment_complete() -> void:
\tprint("Quest complete!")
""",
    "RegisterManager.gd": """\
extends Node

var assets:     Dictionary = {}
var actions:    Dictionary = {}
var states:     Dictionary = {}
var effects:    Dictionary = {}
var conditions: Dictionary = {}

func load_registers(dsl: Dictionary) -> void:
\tvar reg = dsl.get("registers", {})
\tfor a in reg.get("assets", []):
\t\tassets[a["id"]] = a
\tfor a in reg.get("actions", []):
\t\tactions[a["id"]] = a
\tfor s in reg.get("states", []):
\t\tstates[s["id"]] = {"asset": s["asset"], "value": s["value"]}
\tfor e in reg.get("effects", []):
\t\teffects[e["id"]] = {"changes": e["changes"], "to": e["to"]}
\tfor c in reg.get("conditions", []):
\t\tconditions[c["id"]] = {"check": c["check"], "equals": c["equals"]}

func check_condition(cond_id: String, world_state: Dictionary) -> bool:
\tvar cond = conditions.get(cond_id, {})
\tif cond.is_empty():
\t\treturn true
\treturn str(world_state.get(cond["check"], "")) == cond["equals"]

func apply_effect(effect_id: String, world_state: Dictionary) -> void:
\tvar eff = effects.get(effect_id, {})
\tif eff.is_empty():
\t\treturn
\tworld_state[eff["changes"]] = eff["to"]
""",
}

ASSET_TYPE_FOLDERS = {
    "object": "assets/objects",
    "npc":    "assets/npcs",
    "item":   "assets/items",
    "zone":   "assets/zones",
}

# ── Simplified prompt — fewer tokens = fewer truncations ─────────────────────
SYSTEM_PROMPT_INITIAL = """You are GLAM. Output ONLY a single valid JSON object, nothing else.
No markdown. No explanation. No code fences. Just the raw JSON.

Required structure (use SCREAMING_SNAKE_CASE for all IDs):
{
  "meta": {"id": "snake_id", "version": "1.0", "domain": "name"},
  "registers": {
    "assets":     [{"id":"ASSET_ID","type":"object|npc|item|zone","label":"Name"}],
    "actions":    [{"id":"ACTION_ID","label":"Name","target":"ASSET_ID"}],
    "states":     [{"id":"STATE_ID","asset":"ASSET_ID","value":"initial"}],
    "effects":    [{"id":"EFFECT_ID","changes":"STATE_ID","to":"new_value"}],
    "conditions": [{"id":"COND_ID","check":"STATE_ID","equals":"value"}],
    "reactions":  [{"id":"REACTION_ID","on":"ACTION_ID","if":"COND_ID","trigger":"EFFECT_ID"}]
  },
  "dialogue": {"MAIN": {"start": "Hello!", "end": "Goodbye!"}},
  "experiment": {
    "start": "STEP_1",
    "steps": [
      {"state_id":"STEP_1","description":"desc","wire":{"on":"ACTION_ID","condition":"","next":"STEP_2"}},
      {"state_id":"STEP_2","description":"desc","wire":{"on":"ACTION_ID","condition":"","next":"END"}}
    ]
  }
}
Output ONLY the JSON. Start your response with { and end with }."""

SYSTEM_PROMPT_REFINE = """You are GLAM. Apply the requested change to the JSON.
Output ONLY the full updated JSON. Start with { and end with }.
No markdown. No explanation."""


# ─────────────────────────────────────────────────────────────────────────────
#  Robust JSON repair utilities
# ─────────────────────────────────────────────────────────────────────────────
def _close_truncated(fragment: str) -> str:
    """Close any unclosed strings/arrays/objects in a truncated JSON fragment."""
    result = []
    in_str = False
    escape = False
    stack  = []

    for ch in fragment:
        if escape:
            escape = False
            result.append(ch)
            continue
        if ch == "\\" and in_str:
            escape = True
            result.append(ch)
            continue
        if ch == '"':
            in_str = not in_str
            result.append(ch)
            continue
        if in_str:
            result.append(ch)
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch in "]}":
            if stack:
                stack.pop()
        result.append(ch)

    if in_str:
        result.append('"')

    joined = "".join(result).rstrip()
    if joined.endswith(","):
        joined = joined[:-1]

    for opener in reversed(stack):
        joined += "}" if opener == "{" else "]"

    return joined


def _repair_json(raw: str) -> str:
    """Best-effort repair of malformed JSON from small LLMs."""
    # 1. Extract outermost { ... } block
    start = raw.find("{")
    if start == -1:
        raise ValueError("No JSON object found in output")

    depth = 0
    end   = -1
    in_str = False
    escape = False
    for i, ch in enumerate(raw[start:], start):
        if escape:
            escape = False
            continue
        if ch == "\\" and in_str:
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break

    if end == -1:
        raw = _close_truncated(raw[start:])
    else:
        raw = raw[start:end + 1]

    # 2. Common textual fixes
    raw = re.sub(r',\s*([}\]])', r'\1', raw)          # trailing commas
    raw = re.sub(r"'([^']*)'", r'"\1"', raw)           # single → double quotes
    raw = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\1"\2":', raw)  # unquoted keys
    raw = raw.replace(": True",  ': true') \
             .replace(": False", ': false') \
             .replace(": None",  ': null')
    raw = re.sub(r'//[^\n]*', '', raw)                 # JS // comments
    raw = re.sub(r'/\*.*?\*/', '', raw, flags=re.DOTALL)

    return raw


def _parse_with_repair(raw: str) -> dict:
    """Try json.loads, then repair up to two passes. Raises on total failure."""
    raw = raw.strip()

    # Strip accidental markdown fences
    raw = re.sub(r'^```[a-zA-Z]*\n?', '', raw)
    raw = re.sub(r'\n?```$', '', raw)
    raw = raw.strip()

    for attempt, text in enumerate([raw, _repair_json(raw)], 1):
        try:
            result = json.loads(text)
            if attempt > 1:
                print(f"[GLAM] JSON repaired on attempt {attempt}")
            return result
        except json.JSONDecodeError:
            pass

    # Final pass: repair the repaired string
    double_repaired = _repair_json(_repair_json(raw))
    try:
        print("[GLAM] JSON repaired on attempt 3 (double-pass)")
        return json.loads(double_repaired)
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(
            f"Could not repair JSON: {e.msg}\n\n"
            f"--- Last repair attempt ---\n{double_repaired[:600]}",
            e.doc, e.pos
        )


# ─────────────────────────────────────────────────────────────────────────────
#  Worker thread
# ─────────────────────────────────────────────────────────────────────────────
class GenerateWorker(QThread):
    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, prompt: str, system: str):
        super().__init__()
        self.prompt = prompt
        self.system = system

    def run(self):
        try:
            payload = {
                "model": MODEL,
                "prompt": self.system + "\n\nUser idea: " + self.prompt,
                "stream": True,
                "options": {
                    "temperature": 0.1,      # lower = more deterministic
                    "num_thread":  6,
                    "num_predict": 4096,     # enough for a full DSL
                    #"num_ctx":     4096,
                    "stop": ["\n\n\n"]
                }
            }

            resp = requests.post(OLLAMA_URL, json=payload, stream=True, timeout=600)
            resp.raise_for_status()

            full_output = ""
            for line in resp.iter_lines():
                if line:
                    try:
                        chunk = json.loads(line.decode("utf-8"))
                        full_output += chunk.get("response", "")
                    except Exception:
                        continue

            raw = full_output.strip()
            print("\n--- RAW MODEL OUTPUT (first 800 chars) ---\n",
                  raw[:800], "\n---\n")

            parsed = _parse_with_repair(raw)
            self.finished.emit(json.dumps(parsed, indent=2))

        except requests.ConnectionError:
            self.error.emit("Cannot connect to Ollama.\nRun: ollama serve")
        except requests.Timeout:
            self.error.emit("Ollama timed out (>600s).")
        except json.JSONDecodeError as e:
            self.error.emit(f"Model returned invalid JSON even after repair:\n{e}")
        except Exception as e:
            self.error.emit(f"Unexpected error:\n{str(e)}")


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "color: #555D7A; font-size: 10px; font-weight: 700; letter-spacing: 1.5px;"
    )
    return lbl


def _divider() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet("background: #1E2230; max-height: 1px; border: none;")
    return f


# ─────────────────────────────────────────────────────────────────────────────
#  Asset row widget
# ─────────────────────────────────────────────────────────────────────────────
class AssetRow(QFrame):
    file_chosen = pyqtSignal()

    def __init__(self, asset: dict, parent=None):
        super().__init__(parent)
        self.asset     = asset
        self.file_path = None
        self.setObjectName("assetRow")
        self.setStyleSheet("""
            QFrame#assetRow {
                background: #131827;
                border: 1px solid #1E2230;
                border-radius: 8px;
            }
            QFrame#assetRow:hover { border: 1px solid #2A3050; }
        """)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(12)

        meta_col = QVBoxLayout()
        meta_col.setSpacing(3)

        asset_type = asset.get("type", "object")
        type_colors = {
            "object": ("#3A5BD9", "#A8BFFF"),
            "npc":    ("#1D7A50", "#7ECFA0"),
            "item":   ("#7A4A1D", "#FFBD80"),
            "zone":   ("#5A1D7A", "#CF9FFF"),
        }
        bg, fg = type_colors.get(asset_type, ("#2A2D3A", "#AAAAAA"))
        type_badge = QLabel(f"  {asset_type.upper()}  ")
        type_badge.setStyleSheet(
            f"background:{bg}; color:{fg}; border-radius:4px;"
            "padding:2px 6px; font-size:9px; font-weight:700; letter-spacing:1px;"
        )
        type_badge.setFixedHeight(18)
        type_badge.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        id_lbl = QLabel(asset.get("id", "?"))
        id_lbl.setStyleSheet(
            "color:#7EC8E3; font-size:12px; font-weight:700;"
            "font-family:'Consolas','Courier New',monospace;"
        )
        human_lbl = QLabel(asset.get("label", ""))
        human_lbl.setStyleSheet("color:#666E8A; font-size:11px;")

        meta_col.addWidget(type_badge)
        meta_col.addWidget(id_lbl)
        meta_col.addWidget(human_lbl)
        outer.addLayout(meta_col)
        outer.addStretch()

        right_col = QVBoxLayout()
        right_col.setSpacing(6)
        right_col.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.file_lbl = QLabel("No file selected")
        self.file_lbl.setStyleSheet("color:#3A3F55; font-size:11px; font-style:italic;")
        self.file_lbl.setAlignment(Qt.AlignRight)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.btn_pick = QPushButton("Attach File")
        self.btn_pick.setFixedHeight(30)
        self.btn_pick.setStyleSheet("""
            QPushButton {
                background:#1A2040; color:#7EC8E3;
                border:1px solid #2A3560; border-radius:6px;
                padding:0 12px; font-size:11px; font-weight:600;
            }
            QPushButton:hover { background:#1F2B55; border-color:#4F7FFF; }
        """)
        self.btn_pick.clicked.connect(self._pick)

        self.btn_clear = QPushButton("✕")
        self.btn_clear.setFixedSize(30, 30)
        self.btn_clear.setVisible(False)
        self.btn_clear.setStyleSheet("""
            QPushButton {
                background:#2A1A1A; color:#FF8C8C;
                border:1px solid #3A2020; border-radius:6px;
                font-size:11px; font-weight:700;
            }
            QPushButton:hover { background:#3A2020; }
        """)
        self.btn_clear.clicked.connect(self._clear)

        btn_row.addWidget(self.btn_pick)
        btn_row.addWidget(self.btn_clear)
        right_col.addWidget(self.file_lbl)
        right_col.addLayout(btn_row)
        outer.addLayout(right_col)

    def _pick(self):
        path, _ = QFileDialog.getOpenFileName(
            self, f"Attach file for {self.asset.get('id')}", "", "All Files (*.*)"
        )
        if path:
            self.file_path = path
            self.file_lbl.setText(os.path.basename(path))
            self.file_lbl.setStyleSheet("color:#7ECFA0; font-size:11px;")
            self.btn_clear.setVisible(True)
            self.btn_pick.setText("Change")
            self.file_chosen.emit()

    def _clear(self):
        self.file_path = None
        self.file_lbl.setText("No file selected")
        self.file_lbl.setStyleSheet("color:#3A3F55; font-size:11px; font-style:italic;")
        self.btn_clear.setVisible(False)
        self.btn_pick.setText("Attach File")
        self.file_chosen.emit()


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 1 — Idea input panel
# ─────────────────────────────────────────────────────────────────────────────
class StepIdea(QWidget):
    submitted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignTop)

        title = QLabel("What's your game scenario?")
        title.setStyleSheet(
            "color:#E0E0E0; font-size:22px; font-weight:700; letter-spacing:0.5px;"
        )
        sub = QLabel(
            "Describe your idea in plain language. GLAM will generate the full DSL from it."
        )
        sub.setStyleSheet("color:#555D7A; font-size:13px;")
        sub.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(sub)
        layout.addWidget(_divider())

        self.idea_box = QTextEdit()
        self.idea_box.setPlaceholderText(
            "e.g.  A quest where the player talks to a blacksmith, receives a sword, "
            "and then enters a locked dungeon to defeat a guard NPC…"
        )
        self.idea_box.setMinimumHeight(160)
        self.idea_box.setStyleSheet("""
            QTextEdit {
                background:#0F1320; color:#C8D0E8;
                border:1px solid #2A3060; border-radius:10px;
                padding:14px; font-size:13px;
            }
            QTextEdit:focus { border:1px solid #4F7FFF; }
        """)
        layout.addWidget(self.idea_box)

        self.btn_generate = QPushButton("Generate DSL  →")
        self.btn_generate.setFixedHeight(44)
        self.btn_generate.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #3A6FFF, stop:1 #5B3FD9);
                color:#FFFFFF; border-radius:10px;
                font-size:14px; font-weight:700; letter-spacing:0.5px;
                border:none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #4F80FF, stop:1 #7050FF);
            }
            QPushButton:disabled { background:#1A2040; color:#333; }
        """)
        self.btn_generate.clicked.connect(self._submit)
        layout.addWidget(self.btn_generate)

        self.loading_frame = QFrame()
        loading_layout = QVBoxLayout(self.loading_frame)
        loading_layout.setSpacing(8)
        self.loading_lbl = QLabel("Generating DSL…  (15–60s on CPU)")
        self.loading_lbl.setAlignment(Qt.AlignCenter)
        self.loading_lbl.setStyleSheet("color:#4F7FFF; font-size:12px;")
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(4)
        self.progress.setStyleSheet("""
            QProgressBar { background:#1A1E2C; border-radius:2px; border:none; }
            QProgressBar::chunk { background:#4F7FFF; border-radius:2px; }
        """)
        loading_layout.addWidget(self.loading_lbl)
        loading_layout.addWidget(self.progress)
        self.loading_frame.setVisible(False)
        layout.addWidget(self.loading_frame)
        layout.addStretch()

    def _submit(self):
        text = self.idea_box.toPlainText().strip()
        if not text:
            return
        self.submitted.emit(text)

    def set_loading(self, on: bool):
        self.loading_frame.setVisible(on)
        self.btn_generate.setEnabled(not on)
        self.idea_box.setReadOnly(on)


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 2 — Asset file-labeling panel
# ─────────────────────────────────────────────────────────────────────────────
class StepAssets(QWidget):
    confirmed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(16)

        title = QLabel("Attach files to assets")
        title.setStyleSheet("color:#E0E0E0; font-size:22px; font-weight:700;")
        self.sub = QLabel("")
        self.sub.setStyleSheet("color:#555D7A; font-size:13px;")
        self.sub.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(self.sub)
        layout.addWidget(_divider())

        legend_row = QHBoxLayout()
        for t, (bg, fg) in {
            "OBJECT": ("#3A5BD9", "#A8BFFF"),
            "NPC":    ("#1D7A50", "#7ECFA0"),
            "ITEM":   ("#7A4A1D", "#FFBD80"),
            "ZONE":   ("#5A1D7A", "#CF9FFF"),
        }.items():
            badge = QLabel(f"  {t}  ")
            badge.setStyleSheet(
                f"background:{bg}; color:{fg}; border-radius:4px;"
                "padding:2px 8px; font-size:9px; font-weight:700; letter-spacing:1px;"
            )
            legend_row.addWidget(badge)
        legend_row.addStretch()
        layout.addLayout(legend_row)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea { border:none; background:transparent; }")

        self.inner = QWidget()
        self.inner.setStyleSheet("background:transparent;")
        self.inner_layout = QVBoxLayout(self.inner)
        self.inner_layout.setContentsMargins(0, 0, 0, 0)
        self.inner_layout.setSpacing(8)
        self.inner_layout.addStretch()
        self.scroll.setWidget(self.inner)
        layout.addWidget(self.scroll, stretch=1)

        self.note = QLabel(
            "Files are optional — assets without a file will be noted in the bundle but skipped."
        )
        self.note.setStyleSheet("color:#3A3F55; font-size:11px;")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)

        self.btn_confirm = QPushButton("Bundle & Package  →")
        self.btn_confirm.setFixedHeight(44)
        self.btn_confirm.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #1C7A4B, stop:1 #1A5B8A);
                color:#FFFFFF; border-radius:10px;
                font-size:14px; font-weight:700; border:none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #22A060, stop:1 #2070B0);
            }
        """)
        self.btn_confirm.clicked.connect(self.confirmed.emit)
        layout.addWidget(self.btn_confirm)

    def populate(self, dsl: dict):
        for r in self._rows:
            r.deleteLater()
        self._rows.clear()
        while self.inner_layout.count():
            item = self.inner_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        assets  = dsl.get("registers", {}).get("assets", [])
        meta_id = dsl.get("meta", {}).get("id", "?")
        self.sub.setText(
            f'DSL "{meta_id}" has {len(assets)} asset(s). '
            "Attach a game file to each one so GLAM can bundle them correctly."
        )
        for asset in assets:
            row = AssetRow(asset, self.inner)
            self.inner_layout.addWidget(row)
            self._rows.append(row)
        self.inner_layout.addStretch()

    def get_file_map(self) -> dict:
        return {r.asset["id"]: r.file_path for r in self._rows}

    def get_asset_list(self) -> list:
        return [r.asset for r in self._rows]


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 3 — Review & output panel
# ─────────────────────────────────────────────────────────────────────────────
class StepReview(QWidget):
    save_requested = pyqtSignal(str)
    start_over     = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dsl    = None
        self._assets = []
        self._fmap   = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(16)

        title = QLabel("Review & Save")
        title.setStyleSheet("color:#E0E0E0; font-size:22px; font-weight:700;")
        layout.addWidget(title)
        layout.addWidget(_divider())

        layout.addWidget(_section_label("DSL JSON  —  edit before saving"))
        self.json_editor = QTextEdit()
        self.json_editor.setStyleSheet("""
            QTextEdit {
                background:#0F1320; color:#C8D0E8;
                border:1px solid #2A3060; border-radius:10px;
                padding:12px;
                font-family:'Consolas','Courier New',monospace;
                font-size:12px;
            }
        """)
        layout.addWidget(self.json_editor, stretch=1)

        layout.addWidget(_section_label("BUNDLE MANIFEST"))
        self.manifest_lbl = QLabel("")
        self.manifest_lbl.setStyleSheet(
            "color:#556080; font-size:11px; "
            "font-family:'Consolas','Courier New',monospace;"
        )
        self.manifest_lbl.setWordWrap(True)
        layout.addWidget(self.manifest_lbl)
        layout.addWidget(_divider())

        folder_row = QHBoxLayout()
        self.btn_folder = QPushButton("Output Folder")
        self.btn_folder.setFixedHeight(34)
        self.btn_folder.setStyleSheet("""
            QPushButton {
                background:#1A1E2C; color:#8090B0;
                border:1px solid #2A3060; border-radius:8px;
                padding:0 14px; font-size:12px;
            }
            QPushButton:hover { background:#1E2438; color:#FFF; }
        """)
        self.btn_folder.clicked.connect(self._pick_folder)
        self.folder_lbl = QLabel(DEFAULT_OUT)
        self.folder_lbl.setStyleSheet("color:#3A4060; font-size:11px;")
        self.output_folder = DEFAULT_OUT
        folder_row.addWidget(self.btn_folder)
        folder_row.addWidget(self.folder_lbl, stretch=1)
        layout.addLayout(folder_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self.btn_save = QPushButton("Save JSON + ZIP  →")
        self.btn_save.setFixedHeight(44)
        self.btn_save.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #1C7A4B, stop:1 #1A5B8A);
                color:#FFFFFF; border-radius:10px;
                font-size:14px; font-weight:700; border:none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #22A060, stop:1 #2070B0);
            }
        """)
        self.btn_save.clicked.connect(self._do_save)

        self.btn_reset = QPushButton("Start Over")
        self.btn_reset.setFixedHeight(44)
        self.btn_reset.setStyleSheet("""
            QPushButton {
                background:#1A1E2C; color:#8090B0;
                border:1px solid #2A3060; border-radius:10px;
                font-size:13px; font-weight:600;
            }
            QPushButton:hover { background:#2A1A1A; color:#FF8C8C; border-color:#4A2020; }
        """)
        self.btn_reset.clicked.connect(self.start_over.emit)

        btn_row.addWidget(self.btn_save, stretch=1)
        btn_row.addWidget(self.btn_reset)
        layout.addLayout(btn_row)

    def load(self, dsl: dict, assets: list, file_map: dict):
        self._dsl    = dsl
        self._assets = assets
        self._fmap   = file_map
        self.json_editor.setPlainText(json.dumps(dsl, indent=2))
        self._refresh_manifest()

    def _refresh_manifest(self):
        lines = []
        quest_id = self._dsl.get("meta", {}).get("id", "quest")
        lines.append(f"{quest_id}.zip")
        lines.append(f"  ├─ {quest_id}.json")
        lines.append(f"  ├─ scripts/")
        for gd in GDSCRIPTS:
            lines.append(f"  │    ├─ {gd}")
        for asset in self._assets:
            aid    = asset.get("id", "?")
            atype  = asset.get("type", "object")
            fp     = self._fmap.get(aid)
            folder = ASSET_TYPE_FOLDERS.get(atype, "assets/other")
            if fp:
                lines.append(f"  ├─ {folder}/{os.path.basename(fp)}")
            else:
                lines.append(f"  ├─ {folder}/   ← {aid}  (no file attached)")
        self.manifest_lbl.setText("\n".join(lines))

    def _pick_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select output folder", self.output_folder
        )
        if folder:
            self.output_folder = folder
            self.folder_lbl.setText(folder)

    def _do_save(self):
        raw = self.json_editor.toPlainText().strip()
        try:
            dsl = json.loads(raw)
        except json.JSONDecodeError as e:
            QMessageBox.critical(self, "Invalid JSON", f"Fix JSON before saving:\n{e}")
            return
        self._dsl = dsl
        self.save_requested.emit(self.output_folder)


# ─────────────────────────────────────────────────────────────────────────────
#  Main Window
# ─────────────────────────────────────────────────────────────────────────────
class GLAMWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GLAM — Game Logic Automation Middleware")
        self.setMinimumSize(940, 680)
        self._dsl      = None
        self._idea_txt = ""
        self._apply_theme()
        self._build_ui()

    def _apply_theme(self):
        self.setStyleSheet("""
        QMainWindow, QWidget {
            background-color: #0C0F1A;
            color: #E0E0E0;
            font-family: 'Segoe UI', sans-serif;
        }
        QSplitter::handle { background: #1A1E2C; width: 2px; }
        QScrollBar:vertical {
            background: #0C0F1A; width: 6px; border-radius: 3px;
        }
        QScrollBar::handle:vertical {
            background: #2A2D3A; border-radius: 3px; min-height: 20px;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        QStatusBar {
            background: #08090F; color: #2A3050;
            font-size: 11px; border-top: 1px solid #1A1E2C;
        }
        """)

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        top = QFrame()
        top.setFixedHeight(52)
        top.setStyleSheet("background:#08090F; border-bottom:1px solid #12151F;")
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(28, 0, 28, 0)

        logo = QLabel("GLAM")
        logo.setStyleSheet(
            "color:#4F7FFF; font-size:18px; font-weight:800; letter-spacing:4px;"
        )
        wordmark = QLabel("GAME LOGIC AUTOMATION MIDDLEWARE")
        wordmark.setStyleSheet(
            "color:#1E2440; font-size:9px; font-weight:700; letter-spacing:2px;"
        )
        top_layout.addWidget(logo)
        top_layout.addWidget(wordmark)
        top_layout.addStretch()

        self.step_labels = []
        breadcrumb = QHBoxLayout()
        breadcrumb.setSpacing(4)
        for i, txt in enumerate(["1  Idea", "2  Assets", "3  Review"]):
            lbl = QLabel(txt)
            lbl.setFixedHeight(24)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setMinimumWidth(90)
            lbl.setStyleSheet(
                "color:#1E2440; font-size:10px; font-weight:700;"
                "border-radius:4px; padding:0 10px;"
            )
            breadcrumb.addWidget(lbl)
            self.step_labels.append(lbl)
        top_layout.addLayout(breadcrumb)
        root_layout.addWidget(top)

        self.stack = QStackedWidget()
        self.pg_idea   = StepIdea()
        self.pg_assets = StepAssets()
        self.pg_review = StepReview()
        self.stack.addWidget(self.pg_idea)
        self.stack.addWidget(self.pg_assets)
        self.stack.addWidget(self.pg_review)
        root_layout.addWidget(self.stack, stretch=1)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Step 1 — describe your game scenario.")

        self.pg_idea.submitted.connect(self._on_idea_submitted)
        self.pg_assets.confirmed.connect(self._on_assets_confirmed)
        self.pg_review.save_requested.connect(self._on_save)
        self.pg_review.start_over.connect(self._reset)
        self._set_step(0)

    def _set_step(self, idx: int):
        self.stack.setCurrentIndex(idx)
        active_style   = ("color:#E0E0E0; font-size:10px; font-weight:700;"
                          "background:#1A2550; border-radius:4px; padding:0 10px;")
        inactive_style = ("color:#1E2440; font-size:10px; font-weight:700;"
                          "border-radius:4px; padding:0 10px;")
        done_style     = ("color:#22A060; font-size:10px; font-weight:700;"
                          "background:#0E2018; border-radius:4px; padding:0 10px;")
        for i, lbl in enumerate(self.step_labels):
            if i < idx:    lbl.setStyleSheet(done_style)
            elif i == idx: lbl.setStyleSheet(active_style)
            else:          lbl.setStyleSheet(inactive_style)

    def _on_idea_submitted(self, idea: str):
        self._idea_txt = idea
        self.pg_idea.set_loading(True)
        self.status.showMessage("Generating DSL…  please wait.")
        self.worker = GenerateWorker(idea, SYSTEM_PROMPT_INITIAL)
        self.worker.finished.connect(self._on_dsl_ready)
        self.worker.error.connect(self._on_gen_error)
        self.worker.start()

    def _on_dsl_ready(self, json_text: str):
        self.pg_idea.set_loading(False)
        try:
            self._dsl = json.loads(json_text)
        except json.JSONDecodeError as e:
            self._on_gen_error(f"Invalid JSON from model:\n{e}")
            return
        n_assets = len(self._dsl.get("registers", {}).get("assets", []))
        meta_id  = self._dsl.get("meta", {}).get("id", "?")
        self.status.showMessage(
            f'DSL generated: "{meta_id}" — {n_assets} asset(s). Now attach files.'
        )
        self.pg_assets.populate(self._dsl)
        self._set_step(1)

    def _on_gen_error(self, msg: str):
        self.pg_idea.set_loading(False)
        self.status.showMessage("Generation failed — see dialog.")
        QMessageBox.critical(self, "GLAM Error", msg)

    def _on_assets_confirmed(self):
        file_map = self.pg_assets.get_file_map()
        assets   = self.pg_assets.get_asset_list()
        self.pg_review.load(self._dsl, assets, file_map)
        self._set_step(2)
        attached = sum(1 for v in file_map.values() if v)
        self.status.showMessage(
            f"Step 3 — {attached}/{len(assets)} asset(s) have files. Review & save."
        )

    def _on_save(self, output_folder: str):
        raw = self.pg_review.json_editor.toPlainText().strip()
        try:
            dsl = json.loads(raw)
        except json.JSONDecodeError as e:
            QMessageBox.critical(self, "Invalid JSON", str(e))
            return

        file_map = self.pg_assets.get_file_map()
        assets   = self.pg_assets.get_asset_list()
        quest_id = dsl.get("meta", {}).get("id", "quest_unnamed")
        os.makedirs(output_folder, exist_ok=True)

        json_path = os.path.join(output_folder, f"{quest_id}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(dsl, f, indent=2)

        zip_path = os.path.join(output_folder, f"{quest_id}.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(json_path, arcname=f"{quest_id}.json")
            for filename, content in GDSCRIPTS.items():
                zf.writestr(f"scripts/{filename}", content)
            for asset in assets:
                aid    = asset.get("id", "?")
                atype  = asset.get("type", "object")
                fp     = file_map.get(aid)
                if fp and os.path.isfile(fp):
                    folder  = ASSET_TYPE_FOLDERS.get(atype, "assets/other")
                    arcname = f"{folder}/{os.path.basename(fp)}"
                    zf.write(fp, arcname=arcname)

        self.status.showMessage(f"Saved → {json_path}  |  {zip_path}")
        QMessageBox.information(
            self, "Saved!",
            f"JSON:\n  {json_path}\n\nZIP bundle:\n  {zip_path}\n\n"
            f"The ZIP contains:\n"
            f"  • {quest_id}.json\n"
            f"  • scripts/ ({len(GDSCRIPTS)} GDScripts)\n"
            f"  • asset files in typed subfolders"
        )

    def _reset(self):
        reply = QMessageBox.question(
            self, "Start Over",
            "This will clear everything and return to Step 1. Continue?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self._dsl      = None
        self._idea_txt = ""
        self.pg_idea.idea_box.clear()
        self.pg_idea.set_loading(False)
        self._set_step(0)
        self.status.showMessage("Step 1 — describe your game scenario.")


# ─────────────────────────────────────────────────────────────────────────────
#  Entry
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = GLAMWindow()
    w.show()
    sys.exit(app.exec_())