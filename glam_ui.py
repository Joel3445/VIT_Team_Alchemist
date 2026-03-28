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
    QStackedWidget, QProgressBar, QSizePolicy, QButtonGroup,
    QToolButton, QGraphicsDropShadowEffect, QFormLayout, QGridLayout,
    QScrollBar, QPlainTextEdit
)
from PyQt5.QtCore import (
    Qt, QThread, pyqtSignal, QPropertyAnimation, QRect,
    QTimer, QPoint, QSize, QEvent
)
from PyQt5.QtGui import (
    QColor, QTextCharFormat, QSyntaxHighlighter, QFont, QPalette,
    QPainter, QLinearGradient, QFontDatabase, QIcon, QTextCursor,
    QSyntaxHighlighter, QTextDocument
)

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

QNA_QUESTIONS = [
    ("🎯  Quest Goal", "What is the player's main objective?", "e.g. Retrieve the ancient sword from the dungeon"),
    ("👤  Key NPC", "Who is the main NPC the player interacts with?", "e.g. Aldric the Blacksmith"),
    ("🗺️  Setting", "Where does this quest take place?", "e.g. A foggy mountain village with a locked dungeon"),
    ("⚔️  Challenge", "What obstacle or conflict must the player overcome?", "e.g. A guard NPC blocking the dungeon entrance"),
    ("🎁  Reward", "What does the player receive upon completion?", "e.g. A legendary sword and 500 gold coins"),
]

TEMPLATE_FIELDS = [
    ("Quest Name",     "quest_name",     "The Blacksmith's Legacy"),
    ("Domain",         "domain",         "fantasy_village"),
    ("NPC Name",       "npc_name",       "Aldric"),
    ("NPC Type",       "npc_type",       "blacksmith"),
    ("Key Item",       "key_item",       "Ancient Sword"),
    ("Location/Zone",  "zone_name",      "Dungeon of Echoes"),
    ("Objective",      "objective",      "Retrieve the sword and defeat the guard"),
    ("Reward",         "reward",         "500 gold coins"),
]


# ─────────────────────────────────────────────────────────────────────────────
#  JSON Syntax Highlighter
# ─────────────────────────────────────────────────────────────────────────────
class JsonSyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self._rules = []

        # Keys
        key_fmt = QTextCharFormat()
        key_fmt.setForeground(QColor("#79B8FF"))
        key_fmt.setFontWeight(QFont.Bold)
        self._rules.append((re.compile(r'"([^"]+)"\s*:'), key_fmt))

        # String values
        str_fmt = QTextCharFormat()
        str_fmt.setForeground(QColor("#9ECE6A"))
        self._rules.append((re.compile(r':\s*"([^"]*)"'), str_fmt))

        # Numbers
        num_fmt = QTextCharFormat()
        num_fmt.setForeground(QColor("#FF9E64"))
        self._rules.append((re.compile(r'\b(\d+\.?\d*)\b'), num_fmt))

        # Booleans / null
        kw_fmt = QTextCharFormat()
        kw_fmt.setForeground(QColor("#BB9AF7"))
        kw_fmt.setFontWeight(QFont.Bold)
        self._rules.append((re.compile(r'\b(true|false|null)\b'), kw_fmt))

        # Brackets/braces
        br_fmt = QTextCharFormat()
        br_fmt.setForeground(QColor("#E0AF68"))
        self._rules.append((re.compile(r'[{}\[\]]'), br_fmt))

    def highlightBlock(self, text):
        for pattern, fmt in self._rules:
            for m in pattern.finditer(text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


# ─────────────────────────────────────────────────────────────────────────────
#  Line-numbered IDE editor
# ─────────────────────────────────────────────────────────────────────────────
class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor._line_number_width(), 0)

    def paintEvent(self, event):
        self.editor._paint_line_numbers(event)


class IdeEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_number_width)
        self.updateRequest.connect(self._update_line_number_area)
        self._update_line_number_width(0)

        font = QFont("Consolas", 13)
        font.setStyleHint(QFont.Monospace)
        self.setFont(font)
        self.setTabStopDistance(28)

        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1A1B2E;
                color: #C0CAF5;
                border: none;
                border-radius: 0px;
                selection-background-color: #283457;
                font-size: 13px;
            }
            QScrollBar:vertical {
                background: #1A1B2E;
                width: 10px;
            }
            QScrollBar::handle:vertical {
                background: #3B4261;
                border-radius: 5px;
            }
            QScrollBar:horizontal {
                background: #1A1B2E;
                height: 10px;
            }
            QScrollBar::handle:horizontal {
                background: #3B4261;
                border-radius: 5px;
            }
        """)
        self._highlighter = JsonSyntaxHighlighter(self.document())

    def _line_number_width(self):
        digits = max(3, len(str(self.blockCount())))
        return 16 + self.fontMetrics().horizontalAdvance('9') * digits

    def _update_line_number_width(self, _):
        self.setViewportMargins(self._line_number_width(), 0, 0, 0)

    def _update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_number_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self._line_number_width(), cr.height()))

    def _paint_line_numbers(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor("#13141F"))
        block = self.firstVisibleBlock()
        block_num = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        font = QFont("Consolas", 11)
        painter.setFont(font)
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(QColor("#4A5173"))
                painter.drawText(
                    0, top,
                    self.line_number_area.width() - 6,
                    self.fontMetrics().height(),
                    Qt.AlignRight, str(block_num + 1)
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            block_num += 1


# ─────────────────────────────────────────────────────────────────────────────
#  JSON repair utilities (unchanged)
# ─────────────────────────────────────────────────────────────────────────────
def _close_truncated(fragment: str) -> str:
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
    raw = re.sub(r',\s*([}\]])', r'\1', raw)
    raw = re.sub(r"'([^']*)'", r'"\1"', raw)
    raw = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\1"\2":', raw)
    raw = raw.replace(": True", ': true').replace(": False", ': false').replace(": None", ': null')
    raw = re.sub(r'//[^\n]*', '', raw)
    raw = re.sub(r'/\*.*?\*/', '', raw, flags=re.DOTALL)
    return raw


def _parse_with_repair(raw: str) -> dict:
    raw = raw.strip()
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
    double_repaired = _repair_json(_repair_json(raw))
    try:
        return json.loads(double_repaired)
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(
            f"Could not repair JSON: {e.msg}\n\n--- Last repair attempt ---\n{double_repaired[:600]}",
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
                    "temperature": 0.1,
                    "num_thread":  6,
                    "num_predict": 4096,
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
            print("\n--- RAW MODEL OUTPUT (first 800 chars) ---\n", raw[:800], "\n---\n")
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
        "color: #7B89B6; font-size: 12px; font-weight: 700; letter-spacing: 1.5px;"
    )
    return lbl


def _divider() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet("background: #E8EDF5; max-height: 1px; border: none;")
    return f


# ─────────────────────────────────────────────────────────────────────────────
#  Step Progress Bar (replaces old breadcrumb buttons)
# ─────────────────────────────────────────────────────────────────────────────
class StepProgressBar(QWidget):
    def __init__(self, steps, parent=None):
        super().__init__(parent)
        self.steps = steps
        self.current = 0
        self.setFixedHeight(56)
        self.setMinimumWidth(420)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.step_widgets = []
        for i, label in enumerate(steps):
            step_w = QWidget()
            step_layout = QHBoxLayout(step_w)
            step_layout.setContentsMargins(0, 0, 0, 0)
            step_layout.setSpacing(6)

            circle = QLabel(str(i + 1))
            circle.setFixedSize(28, 28)
            circle.setAlignment(Qt.AlignCenter)
            circle.setObjectName(f"circle_{i}")
            circle.setStyleSheet(
                "border-radius: 14px; font-size: 12px; font-weight: 800;"
                "background: #CBD5E1; color: #94A3B8;"
            )

            lbl = QLabel(label)
            lbl.setObjectName(f"steplbl_{i}")
            lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #94A3B8;")

            step_layout.addWidget(circle)
            step_layout.addWidget(lbl)
            self.step_widgets.append((circle, lbl))
            layout.addWidget(step_w)

            if i < len(steps) - 1:
                connector = QFrame()
                connector.setFixedHeight(2)
                connector.setMinimumWidth(30)
                connector.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                connector.setObjectName(f"connector_{i}")
                connector.setStyleSheet("background: #E2E8F0; border: none; margin: 0 6px;")
                self.step_widgets.append(("connector", connector))
                layout.addWidget(connector)

        self._refresh()

    def set_step(self, idx: int):
        self.current = idx
        self._refresh()

    def _refresh(self):
        wi = 0
        for i in range(len(self.steps)):
            circle, lbl = self.step_widgets[wi]
            wi += 1
            if i < self.current:
                circle.setStyleSheet(
                    "border-radius: 14px; font-size: 12px; font-weight: 800;"
                    "background: #10B981; color: white;"
                )
                circle.setText("✓")
                lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #10B981;")
            elif i == self.current:
                circle.setStyleSheet(
                    "border-radius: 14px; font-size: 12px; font-weight: 800;"
                    "background: #3B82F6; color: white;"
                )
                circle.setText(str(i + 1))
                lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #1E40AF;")
            else:
                circle.setStyleSheet(
                    "border-radius: 14px; font-size: 12px; font-weight: 800;"
                    "background: #E2E8F0; color: #94A3B8;"
                )
                circle.setText(str(i + 1))
                lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #CBD5E1;")

            if wi < len(self.step_widgets):
                tag, connector = self.step_widgets[wi]
                if tag == "connector":
                    if i < self.current:
                        connector.setStyleSheet("background: #10B981; border: none; margin: 0 6px;")
                    else:
                        connector.setStyleSheet("background: #E2E8F0; border: none; margin: 0 6px;")
                    wi += 1


# ─────────────────────────────────────────────────────────────────────────────
#  QnA Chat Bubble widget
# ─────────────────────────────────────────────────────────────────────────────
class QnABubble(QFrame):
    answered = pyqtSignal(int, str)

    def __init__(self, index, emoji, question, placeholder, parent=None):
        super().__init__(parent)
        self.index = index
        self._answered = False
        self.setObjectName("qnaBubble")
        self.setStyleSheet("""
            QFrame#qnaBubble {
                background: #F0F7FF;
                border: 1.5px solid #BFDBFE;
                border-radius: 14px;
            }
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)

        header = QHBoxLayout()
        emoji_lbl = QLabel(emoji)
        emoji_lbl.setStyleSheet("font-size: 20px;")
        q_lbl = QLabel(question)
        q_lbl.setStyleSheet(
            "color: #1E3A8A; font-size: 14px; font-weight: 700;"
        )
        q_lbl.setWordWrap(True)
        header.addWidget(emoji_lbl)
        header.addWidget(q_lbl, stretch=1)
        layout.addLayout(header)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self.answer_edit = QLineEdit()
        self.answer_edit.setPlaceholderText(placeholder)
        self.answer_edit.setFixedHeight(40)
        self.answer_edit.setStyleSheet("""
            QLineEdit {
                background: white;
                color: #0F172A;
                border: 1.5px solid #BFDBFE;
                border-radius: 8px;
                padding: 0 12px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 1.5px solid #3B82F6;
            }
        """)
        self.answer_edit.returnPressed.connect(self._submit)

        self.btn_ok = QPushButton("✓")
        self.btn_ok.setFixedSize(40, 40)
        self.btn_ok.setStyleSheet("""
            QPushButton {
                background: #3B82F6;
                color: white;
                border: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 700;
            }
            QPushButton:hover { background: #2563EB; }
        """)
        self.btn_ok.clicked.connect(self._submit)

        input_row.addWidget(self.answer_edit, stretch=1)
        input_row.addWidget(self.btn_ok)
        layout.addLayout(input_row)

        self.check_lbl = QLabel("")
        self.check_lbl.setStyleSheet("color: #10B981; font-size: 12px; font-weight: 600;")
        layout.addWidget(self.check_lbl)

    def _submit(self):
        val = self.answer_edit.text().strip()
        if val:
            self._answered = True
            self.check_lbl.setText(f"✓  Noted: {val[:60]}")
            self.setStyleSheet("""
                QFrame#qnaBubble {
                    background: #F0FDF4;
                    border: 1.5px solid #86EFAC;
                    border-radius: 14px;
                }
            """)
            self.answer_edit.setEnabled(False)
            self.btn_ok.setEnabled(False)
            self.answered.emit(self.index, val)

    def get_answer(self):
        return self.answer_edit.text().strip()


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 1 — Idea input panel (Free-form + Template modes + QnA)
# ─────────────────────────────────────────────────────────────────────────────
class StepIdea(QWidget):
    submitted = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._qna_answers = {}
        self._mode = "freeform"   # or "template"
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(60, 44, 60, 44)
        layout.setSpacing(20)

        # Title
        title = QLabel("What's your game scenario?")
        title.setStyleSheet(
            "color:#0F172A; font-size:30px; font-weight:800; letter-spacing:-0.5px;"
        )
        sub = QLabel(
            "Describe your quest idea in plain language — GLAM will build the full DSL."
        )
        sub.setStyleSheet("color:#64748B; font-size:15px;")
        sub.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(sub)
        layout.addWidget(_divider())

        # Mode toggle
        mode_row = QHBoxLayout()
        mode_row.setSpacing(0)
        self.btn_freeform = QPushButton("✏️  Free Form")
        self.btn_template = QPushButton("📋  Template")
        for btn in [self.btn_freeform, self.btn_template]:
            btn.setFixedHeight(38)
            btn.setCheckable(True)
            btn.setStyleSheet("""
                QPushButton {
                    background: #F1F5F9;
                    color: #64748B;
                    border: 1.5px solid #E2E8F0;
                    padding: 0 22px;
                    font-size: 13px;
                    font-weight: 600;
                }
                QPushButton:checked {
                    background: #3B82F6;
                    color: white;
                    border-color: #3B82F6;
                }
                QPushButton:hover:!checked { background: #E2E8F0; }
            """)
        self.btn_freeform.setStyleSheet(
            self.btn_freeform.styleSheet() +
            "QPushButton { border-radius: 8px 0 0 8px; }"
        )
        self.btn_template.setStyleSheet(
            self.btn_template.styleSheet() +
            "QPushButton { border-radius: 0 8px 8px 0; border-left: none; }"
        )
        self.btn_freeform.setChecked(True)
        self.btn_freeform.clicked.connect(lambda: self._switch_mode("freeform"))
        self.btn_template.clicked.connect(lambda: self._switch_mode("template"))
        mode_row.addWidget(self.btn_freeform)
        mode_row.addWidget(self.btn_template)
        mode_row.addStretch()
        layout.addLayout(mode_row)

        # Stacked input area
        self.input_stack = QStackedWidget()

        # Freeform page
        ff_page = QWidget()
        ff_layout = QVBoxLayout(ff_page)
        ff_layout.setContentsMargins(0, 0, 0, 0)
        self.idea_box = QTextEdit()
        self.idea_box.setPlaceholderText(
            "e.g.  A quest where the player talks to a blacksmith, receives a sword, "
            "and then enters a locked dungeon to defeat a guard NPC…"
        )
        self.idea_box.setMinimumHeight(140)
        self.idea_box.setStyleSheet("""
            QTextEdit {
                background: white;
                color: #0F172A;
                border: 2px solid #E2E8F0;
                border-radius: 12px;
                padding: 16px;
                font-size: 15px;
                line-height: 1.6;
            }
            QTextEdit:focus { border: 2px solid #3B82F6; }
        """)
        ff_layout.addWidget(self.idea_box)
        self.input_stack.addWidget(ff_page)

        # Template page
        tmpl_page = QWidget()
        tmpl_layout = QFormLayout(tmpl_page)
        tmpl_layout.setContentsMargins(0, 8, 0, 0)
        tmpl_layout.setSpacing(12)
        tmpl_layout.setLabelAlignment(Qt.AlignRight)
        self.tmpl_fields = {}
        for label, key, placeholder in TEMPLATE_FIELDS:
            le = QLineEdit()
            le.setPlaceholderText(placeholder)
            le.setFixedHeight(40)
            le.setStyleSheet("""
                QLineEdit {
                    background: white;
                    color: #0F172A;
                    border: 1.5px solid #E2E8F0;
                    border-radius: 8px;
                    padding: 0 14px;
                    font-size: 14px;
                }
                QLineEdit:focus { border-color: #3B82F6; }
            """)
            lbl = QLabel(label + ":")
            lbl.setStyleSheet("color: #374151; font-size: 13px; font-weight: 600;")
            tmpl_layout.addRow(lbl, le)
            self.tmpl_fields[key] = le
        self.input_stack.addWidget(tmpl_page)

        layout.addWidget(self.input_stack)

        # QnA section
        qna_header = QHBoxLayout()
        qna_title = QLabel("🤖  Help GLAM understand your vision  —  answer any or all:")
        qna_title.setStyleSheet(
            "color: #1E40AF; font-size: 13px; font-weight: 700;"
        )
        qna_header.addWidget(qna_title)
        qna_header.addStretch()
        layout.addLayout(qna_header)

        qna_scroll = QScrollArea()
        qna_scroll.setWidgetResizable(True)
        qna_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        qna_scroll.setFixedHeight(230)
        qna_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        qna_inner = QWidget()
        qna_inner.setStyleSheet("background: transparent;")
        qna_inner_layout = QVBoxLayout(qna_inner)
        qna_inner_layout.setSpacing(10)
        qna_inner_layout.setContentsMargins(0, 0, 8, 0)

        self.qna_bubbles = []
        for i, (emoji, question, placeholder) in enumerate(QNA_QUESTIONS):
            bubble = QnABubble(i, emoji, question, placeholder)
            bubble.answered.connect(self._on_qna_answered)
            qna_inner_layout.addWidget(bubble)
            self.qna_bubbles.append(bubble)
        qna_inner_layout.addStretch()
        qna_scroll.setWidget(qna_inner)
        layout.addWidget(qna_scroll)

        # Generate button
        self.btn_generate = QPushButton("Generate DSL  →")
        self.btn_generate.setFixedHeight(52)
        self.btn_generate.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #3B82F6, stop:1 #8B5CF6);
                color: white;
                border: none;
                border-radius: 12px;
                font-size: 16px;
                font-weight: 800;
                letter-spacing: 0.4px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #2563EB, stop:1 #7C3AED);
            }
            QPushButton:disabled { background: #CBD5E1; color: #94A3B8; }
        """)
        self.btn_generate.clicked.connect(self._submit)
        layout.addWidget(self.btn_generate)

        # Loading frame
        self.loading_frame = QFrame()
        self.loading_frame.setStyleSheet(
            "background: #EFF6FF; border: 1.5px solid #BFDBFE; border-radius: 12px;"
        )
        load_inner = QVBoxLayout(self.loading_frame)
        load_inner.setContentsMargins(20, 16, 20, 16)
        load_inner.setSpacing(10)
        self.loading_lbl = QLabel("🧠  GLAM is thinking…  (may take 15–60s on CPU)")
        self.loading_lbl.setAlignment(Qt.AlignCenter)
        self.loading_lbl.setStyleSheet("color: #2563EB; font-size: 14px; font-weight: 700;")
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(8)
        self.progress.setStyleSheet("""
            QProgressBar { background: #BFDBFE; border-radius: 4px; border: none; }
            QProgressBar::chunk {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #3B82F6, stop:1 #8B5CF6);
                border-radius: 4px;
            }
        """)
        load_inner.addWidget(self.loading_lbl)
        load_inner.addWidget(self.progress)
        self.loading_frame.setVisible(False)
        layout.addWidget(self.loading_frame)

    def _switch_mode(self, mode):
        self._mode = mode
        if mode == "freeform":
            self.input_stack.setCurrentIndex(0)
            self.btn_freeform.setChecked(True)
            self.btn_template.setChecked(False)
        else:
            self.input_stack.setCurrentIndex(1)
            self.btn_template.setChecked(True)
            self.btn_freeform.setChecked(False)

    def _on_qna_answered(self, idx, val):
        self._qna_answers[idx] = val

    def _build_prompt(self):
        qna_parts = []
        for i, (emoji, question, _) in enumerate(QNA_QUESTIONS):
            if i in self._qna_answers and self._qna_answers[i]:
                qna_parts.append(f"- {question}: {self._qna_answers[i]}")

        if self._mode == "freeform":
            base = self.idea_box.toPlainText().strip()
        else:
            parts = []
            for label, key, _ in TEMPLATE_FIELDS:
                val = self.tmpl_fields[key].text().strip()
                if val:
                    parts.append(f"{label}: {val}")
            base = "\n".join(parts)

        if not base and not qna_parts:
            return None

        prompt = base
        if qna_parts:
            prompt += "\n\nAdditional context from designer:\n" + "\n".join(qna_parts)
        return prompt

    def _submit(self):
        prompt = self._build_prompt()
        if not prompt:
            QMessageBox.information(self, "Empty", "Please fill in your idea or template fields.")
            return
        self.submitted.emit(prompt)

    def set_loading(self, on: bool):
        self.loading_frame.setVisible(on)
        self.btn_generate.setEnabled(not on)
        self.idea_box.setReadOnly(on)
        for le in self.tmpl_fields.values():
            le.setEnabled(not on)


# ─────────────────────────────────────────────────────────────────────────────
#  Asset row
# ─────────────────────────────────────────────────────────────────────────────
class AssetRow(QFrame):
    file_chosen = pyqtSignal()

    def __init__(self, asset: dict, parent=None):
        super().__init__(parent)
        self.asset     = asset
        self.file_path = None
        self._build()

    def _build(self):
        self.setObjectName("assetRow")
        self.setStyleSheet("""
            QFrame#assetRow {
                background: #F8FAFC;
                border: 1.5px solid #E2E8F0;
                border-radius: 12px;
            }
            QFrame#assetRow:hover {
                background: #FFFFFF;
                border: 1.5px solid #CBD5E1;
            }
        """)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(14)

        meta_col = QVBoxLayout()
        meta_col.setSpacing(4)

        asset_type = self.asset.get("type", "object")
        type_colors = {
            "object": ("#DBEAFE", "#1E40AF"),
            "npc":    ("#DCFCE7", "#166534"),
            "item":   ("#FEF3C7", "#92400E"),
            "zone":   ("#F3E8FF", "#6B21A8"),
        }
        bg, fg = type_colors.get(asset_type, ("#F3F4F6", "#6B7280"))
        type_badge = QLabel(f"  {asset_type.upper()}  ")
        type_badge.setStyleSheet(
            f"background:{bg}; color:{fg}; border-radius:6px;"
            "padding:4px 10px; font-size:11px; font-weight:700; letter-spacing:0.5px;"
        )
        type_badge.setFixedHeight(24)
        type_badge.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        id_lbl = QLabel(self.asset.get("id", "?"))
        id_lbl.setStyleSheet(
            "color:#0F172A; font-size:14px; font-weight:800;"
            "font-family:'Consolas','Courier New',monospace;"
        )
        human_lbl = QLabel(self.asset.get("label", ""))
        human_lbl.setStyleSheet("color:#64748B; font-size:13px; font-weight:500;")

        meta_col.addWidget(type_badge)
        meta_col.addWidget(id_lbl)
        meta_col.addWidget(human_lbl)
        outer.addLayout(meta_col)
        outer.addStretch()

        right_col = QVBoxLayout()
        right_col.setSpacing(6)
        right_col.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.file_lbl = QLabel("No file selected")
        self.file_lbl.setStyleSheet("color:#94A3B8; font-size:12px; font-style:italic;")
        self.file_lbl.setAlignment(Qt.AlignRight)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_pick = QPushButton("Attach File")
        self.btn_pick.setFixedHeight(36)
        self.btn_pick.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #3B82F6, stop:1 #2563EB);
                color: white; border: none; border-radius: 8px;
                padding: 0 16px; font-size: 13px; font-weight: 600;
            }
            QPushButton:hover { background: #1D4ED8; }
        """)
        self.btn_pick.clicked.connect(self._pick)

        self.btn_clear = QPushButton("✕")
        self.btn_clear.setFixedSize(36, 36)
        self.btn_clear.setVisible(False)
        self.btn_clear.setStyleSheet("""
            QPushButton {
                background: #FEE2E2; color: #DC2626;
                border: 1.5px solid #FECACA; border-radius: 8px;
                font-size: 13px; font-weight: 700;
            }
            QPushButton:hover { background: #FCA5A5; }
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
            self.file_lbl.setStyleSheet("color:#16A34A; font-size:12px; font-weight:600;")
            self.btn_clear.setVisible(True)
            self.btn_pick.setText("Change")
            self.file_chosen.emit()

    def _clear(self):
        self.file_path = None
        self.file_lbl.setText("No file selected")
        self.file_lbl.setStyleSheet("color:#94A3B8; font-size:12px; font-style:italic;")
        self.btn_clear.setVisible(False)
        self.btn_pick.setText("Attach File")
        self.file_chosen.emit()


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 2 — Asset labeling panel with type filter chips
# ─────────────────────────────────────────────────────────────────────────────
class StepAssets(QWidget):
    confirmed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list = []
        self._active_filter = "all"
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(60, 44, 60, 40)
        layout.setSpacing(18)

        title = QLabel("Attach files to assets")
        title.setStyleSheet("color: #0F172A; font-size: 28px; font-weight: 800;")
        self.sub = QLabel("")
        self.sub.setStyleSheet("color: #64748B; font-size: 15px;")
        self.sub.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(self.sub)
        layout.addWidget(_divider())

        # Filter chip bar
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        self._filter_btns = {}
        chip_defs = [
            ("all",    "All",    "#E2E8F0", "#334155"),
            ("object", "Object", "#DBEAFE", "#1E40AF"),
            ("npc",    "NPC",    "#DCFCE7", "#166534"),
            ("item",   "Item",   "#FEF3C7", "#92400E"),
            ("zone",   "Zone",   "#F3E8FF", "#6B21A8"),
        ]
        for key, label, bg, fg in chip_defs:
            btn = QPushButton(label)
            btn.setFixedHeight(32)
            btn.setCheckable(True)
            btn.setProperty("chip_key", key)
            btn.setProperty("chip_bg", bg)
            btn.setProperty("chip_fg", fg)
            btn.setStyleSheet(
                f"QPushButton {{ background:{bg}; color:{fg}; border:1.5px solid {bg};"
                "border-radius: 8px; padding: 0 14px; font-size: 12px; font-weight: 700; }"
                f"QPushButton:checked {{ background:{fg}; color: white; border-color:{fg}; }}"
                "QPushButton:hover { opacity: 0.85; }"
            )
            btn.clicked.connect(lambda checked, k=key: self._apply_filter(k))
            self._filter_btns[key] = btn
            filter_row.addWidget(btn)
        filter_row.addStretch()
        self._filter_btns["all"].setChecked(True)
        layout.addLayout(filter_row)

        self.count_lbl = QLabel("")
        self.count_lbl.setStyleSheet("color: #94A3B8; font-size: 12px; font-weight: 500;")
        layout.addWidget(self.count_lbl)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { background:#F1F5F9; width:8px; border-radius:4px; }
            QScrollBar::handle:vertical { background:#CBD5E1; border-radius:4px; }
        """)
        self.inner = QWidget()
        self.inner.setStyleSheet("background:transparent;")
        self.inner_layout = QVBoxLayout(self.inner)
        self.inner_layout.setContentsMargins(0, 0, 8, 0)
        self.inner_layout.setSpacing(10)
        self.inner_layout.addStretch()
        self.scroll.setWidget(self.inner)
        layout.addWidget(self.scroll, stretch=1)

        self.note = QLabel(
            "Files are optional — assets without a file will be noted in the bundle but skipped."
        )
        self.note.setStyleSheet("color: #94A3B8; font-size: 13px; font-weight: 500;")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)

        self.btn_confirm = QPushButton("Bundle & Package  →")
        self.btn_confirm.setFixedHeight(52)
        self.btn_confirm.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #10B981, stop:1 #0EA5E9);
                color: white; border-radius: 12px; font-size: 16px;
                font-weight: 800; border: none;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #059669, stop:1 #0284C7);
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
            f'DSL "{meta_id}"  ·  {len(assets)} asset(s) found. '
            "Use filters to browse by type."
        )
        for asset in assets:
            row = AssetRow(asset, self.inner)
            row.file_chosen.connect(self._update_count)
            self.inner_layout.addWidget(row)
            self._rows.append(row)
        self.inner_layout.addStretch()
        self._apply_filter("all")

    def _apply_filter(self, key):
        self._active_filter = key
        for k, btn in self._filter_btns.items():
            btn.setChecked(k == key)

        visible = 0
        for row in self._rows:
            show = (key == "all") or (row.asset.get("type", "") == key)
            row.setVisible(show)
            if show:
                visible += 1

        if key == "all":
            self.count_lbl.setText(f"Showing all {len(self._rows)} assets")
        else:
            self.count_lbl.setText(f"Showing {visible} {key}(s)")

    def _update_count(self):
        attached = sum(1 for r in self._rows if r.file_path)
        self.note.setText(
            f"Files are optional — {attached}/{len(self._rows)} attached.  "
            "Assets without a file will be noted but skipped."
        )

    def get_file_map(self) -> dict:
        return {r.asset["id"]: r.file_path for r in self._rows}

    def get_asset_list(self) -> list:
        return [r.asset for r in self._rows]


# ─────────────────────────────────────────────────────────────────────────────
#  Floating Manifest Button + Popup
# ─────────────────────────────────────────────────────────────────────────────
class ManifestPopup(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("manifestPopup")
        self.setFixedWidth(380)
        self.setStyleSheet("""
            QFrame#manifestPopup {
                background: #1A1B2E;
                border: 1.5px solid #3B4261;
                border-radius: 14px;
            }
        """)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)

        header = QLabel("📦  BUNDLE MANIFEST")
        header.setStyleSheet(
            "color: #7B89B6; font-size: 11px; font-weight: 800; letter-spacing: 1.5px;"
        )
        layout.addWidget(header)
        layout.addWidget(_divider())

        self.content = QLabel("")
        self.content.setStyleSheet(
            "color: #C0CAF5; font-size: 12px; font-family: 'Consolas', monospace; "
            "line-height: 1.6;"
        )
        self.content.setWordWrap(True)
        self.content.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.content)
        self.hide()

    def set_text(self, text):
        self.content.setText(text)
        self.adjustSize()


class FloatingManifestBtn(QPushButton):
    def __init__(self, parent=None):
        super().__init__("📦", parent)
        self.setFixedSize(52, 52)
        self.setToolTip("View Bundle Manifest")
        self.setStyleSheet("""
            QPushButton {
                background: #1E293B;
                color: white;
                border: 1.5px solid #334155;
                border-radius: 26px;
                font-size: 22px;
            }
            QPushButton:hover {
                background: #334155;
                border-color: #3B82F6;
            }
        """)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 100))
        self.setGraphicsEffect(shadow)

        self._popup = ManifestPopup(parent)
        self._popup.hide()
        self._visible = False

        self.clicked.connect(self._toggle)
        self.enterEvent = self._on_enter
        self.leaveEvent = self._on_leave

    def _on_enter(self, e):
        self._show_popup()

    def _on_leave(self, e):
        # Hide only if mouse not over popup
        QTimer.singleShot(200, self._maybe_hide)

    def _maybe_hide(self):
        if not self._popup.underMouse():
            self._popup.hide()
            self._visible = False

    def _toggle(self):
        if self._visible:
            self._popup.hide()
            self._visible = False
        else:
            self._show_popup()

    def _show_popup(self):
        popup = self._popup
        btn_pos = self.mapToParent(QPoint(0, 0))
        popup.adjustSize()
        x = btn_pos.x() - popup.width() - 10
        y = btn_pos.y() - popup.height() + self.height()
        if x < 0:
            x = btn_pos.x() + self.width() + 10
        popup.move(x, y)
        popup.show()
        popup.raise_()
        self._visible = True

    def set_manifest(self, text):
        self._popup.set_text(text)

    def reposition(self, parent_rect):
        margin = 20
        self.move(parent_rect.width() - self.width() - margin,
                  parent_rect.height() - self.height() - margin)
        if self._visible:
            self._show_popup()


# ─────────────────────────────────────────────────────────────────────────────
#  STEP 3 — Review & output panel with IDE editor + floating manifest
# ─────────────────────────────────────────────────────────────────────────────
class StepReview(QWidget):
    save_requested = pyqtSignal(str)
    start_over     = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dsl    = None
        self._assets = []
        self._fmap   = {}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top strip
        top_strip = QFrame()
        top_strip.setFixedHeight(56)
        top_strip.setStyleSheet("background: #0F172A; border-bottom: 1.5px solid #1E293B;")
        strip_layout = QHBoxLayout(top_strip)
        strip_layout.setContentsMargins(24, 0, 24, 0)

        title = QLabel("Review & Save")
        title.setStyleSheet("color: #E2E8F0; font-size: 18px; font-weight: 800;")
        strip_layout.addWidget(title)
        strip_layout.addStretch()

        # Tab bar for editor
        for tab_label, color in [("  DSL.json  ", "#3B82F6")]:
            tab = QLabel(tab_label)
            tab.setStyleSheet(
                f"color: #C0CAF5; background: #1A1B2E; border-top: 2px solid {color};"
                "padding: 4px 16px; font-size: 13px; font-weight: 700;"
                "font-family: 'Consolas', monospace; border-radius: 4px 4px 0 0;"
            )
            strip_layout.addWidget(tab)

        layout.addWidget(top_strip)

        # Main content splitter-like area
        content = QWidget()
        content.setStyleSheet("background: #1A1B2E;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self.json_editor = IdeEditor()
        content_layout.addWidget(self.json_editor, stretch=1)

        layout.addWidget(content, stretch=1)

        # Bottom action bar
        bottom_bar = QFrame()
        bottom_bar.setFixedHeight(72)
        bottom_bar.setStyleSheet(
            "background: #FFFFFF; border-top: 1.5px solid #E2E8F0;"
        )
        bar_layout = QHBoxLayout(bottom_bar)
        bar_layout.setContentsMargins(24, 0, 24, 0)
        bar_layout.setSpacing(12)

        self.btn_folder = QPushButton("📁  Output Folder")
        self.btn_folder.setFixedHeight(42)
        self.btn_folder.setStyleSheet("""
            QPushButton {
                background: #F1F5F9; color: #334155;
                border: 1.5px solid #E2E8F0; border-radius: 10px;
                padding: 0 16px; font-size: 13px; font-weight: 600;
            }
            QPushButton:hover { background: #E2E8F0; }
        """)
        self.btn_folder.clicked.connect(self._pick_folder)

        self.folder_lbl = QLabel(DEFAULT_OUT)
        self.folder_lbl.setStyleSheet("color: #64748B; font-size: 12px; font-weight: 500;")
        self.output_folder = DEFAULT_OUT

        self.btn_save = QPushButton("💾  Save JSON + ZIP  →")
        self.btn_save.setFixedHeight(42)
        self.btn_save.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #10B981, stop:1 #0EA5E9);
                color: white; border-radius: 10px; font-size: 14px;
                font-weight: 800; border: none; padding: 0 20px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #059669, stop:1 #0284C7);
            }
        """)
        self.btn_save.clicked.connect(self._do_save)

        self.btn_reset = QPushButton("Start Over")
        self.btn_reset.setFixedHeight(42)
        self.btn_reset.setStyleSheet("""
            QPushButton {
                background: #F1F5F9; color: #334155;
                border: 1.5px solid #E2E8F0; border-radius: 10px;
                font-size: 13px; font-weight: 600; padding: 0 16px;
            }
            QPushButton:hover { background: #E2E8F0; color: #0F172A; }
        """)
        self.btn_reset.clicked.connect(self.start_over.emit)

        bar_layout.addWidget(self.btn_folder)
        bar_layout.addWidget(self.folder_lbl, stretch=1)
        bar_layout.addWidget(self.btn_reset)
        bar_layout.addWidget(self.btn_save)
        layout.addWidget(bottom_bar)

        # Floating manifest button — parented to self, positioned in resizeEvent
        self.manifest_btn = FloatingManifestBtn(self)
        self.manifest_btn.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.manifest_btn.reposition(self.rect())

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
                lines.append(f"  ├─ {folder}/  ← {aid}  (no file)")
        self.manifest_btn.set_manifest("\n".join(lines))

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
        self.setMinimumSize(1060, 780)
        self._dsl      = None
        self._idea_txt = ""
        self._apply_theme()
        self._build_ui()

    def _apply_theme(self):
        self.setStyleSheet("""
        QMainWindow, QWidget {
            background-color: #FFFFFF;
            color: #0F172A;
            font-family: 'Segoe UI', -apple-system, sans-serif;
        }
        QScrollBar:vertical {
            background: #F1F5F9; width: 8px; border-radius: 4px;
        }
        QScrollBar::handle:vertical {
            background: #CBD5E1; border-radius: 4px; min-height: 20px;
        }
        QScrollBar::handle:vertical:hover { background: #94A3B8; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        QStatusBar {
            background: #F8FAFC; color: #64748B;
            font-size: 13px; font-weight: 500;
            border-top: 1px solid #E2E8F0; padding: 4px 12px;
        }
        """)

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Top bar ──────────────────────────────────────────────────────────
        top = QFrame()
        top.setFixedHeight(64)
        top.setStyleSheet(
            "background: #FFFFFF; border-bottom: 1.5px solid #E2E8F0;"
        )
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(32, 0, 32, 0)
        top_layout.setSpacing(12)

        logo = QLabel("GLAM")
        logo.setStyleSheet(
            "color: #3B82F6; font-size: 22px; font-weight: 900; letter-spacing: 3px;"
        )
        wordmark = QLabel("GAME LOGIC AUTOMATION MIDDLEWARE")
        wordmark.setStyleSheet(
            "color: #94A3B8; font-size: 10px; font-weight: 700; letter-spacing: 2px;"
        )
        top_layout.addWidget(logo)
        top_layout.addWidget(wordmark)
        top_layout.addStretch()

        # Step progress bar
        self.step_bar = StepProgressBar(["Describe Idea", "Attach Assets", "Review & Save"])
        top_layout.addWidget(self.step_bar)
        root_layout.addWidget(top)

        # ── Page stack ───────────────────────────────────────────────────────
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
        self.status.showMessage("Step 1 — describe your game scenario and answer GLAM's questions.")

        self.pg_idea.submitted.connect(self._on_idea_submitted)
        self.pg_assets.confirmed.connect(self._on_assets_confirmed)
        self.pg_review.save_requested.connect(self._on_save)
        self.pg_review.start_over.connect(self._reset)
        self._set_step(0)

    def _set_step(self, idx: int):
        self.stack.setCurrentIndex(idx)
        self.step_bar.set_step(idx)

    def _on_idea_submitted(self, idea: str):
        self._idea_txt = idea
        self.pg_idea.set_loading(True)
        self.status.showMessage("🧠  Generating DSL…  please wait.")
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
            f'✅  DSL generated: "{meta_id}" — {n_assets} asset(s). Now attach files.'
        )
        self.pg_assets.populate(self._dsl)
        self._set_step(1)

    def _on_gen_error(self, msg: str):
        self.pg_idea.set_loading(False)
        self.status.showMessage("❌  Generation failed — see dialog.")
        QMessageBox.critical(self, "GLAM Error", msg)

    def _on_assets_confirmed(self):
        file_map = self.pg_assets.get_file_map()
        assets   = self.pg_assets.get_asset_list()
        self.pg_review.load(self._dsl, assets, file_map)
        self._set_step(2)
        attached = sum(1 for v in file_map.values() if v)
        self.status.showMessage(
            f"Step 3 — {attached}/{len(assets)} asset(s) attached. Review JSON & save."
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

        self.status.showMessage(f"✅  Saved → {json_path}  |  {zip_path}")
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