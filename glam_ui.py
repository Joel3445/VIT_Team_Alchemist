import sys
import json
import os
import requests
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QLabel, QLineEdit, QFileDialog,
    QSplitter, QFrame, QStatusBar, QMessageBox, QScrollArea
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QTextCharFormat, QSyntaxHighlighter

# ── Config ───────────────────────────────────────────────────────────────────
OLLAMA_URL  = "http://localhost:11434/api/generate"
MODEL       = "mistral"
DEFAULT_OUT = os.path.join(os.path.expanduser("~"), "godot_project", "data", "quests")

SYSTEM_PROMPT_INITIAL = """
You are GLAM — Game Logic Automation Middleware.
Convert the user's game idea into a structured JSON using this EXACT schema.
Output ONLY valid JSON. No markdown, no explanation, no code blocks.

{
  "meta": {
    "id": "snake_case_unique_id",
    "version": "1.0",
    "domain": "arena_name"
  },
  "registers": {
    "assets": [
      {"id": "ASSET_ID", "type": "object|npc|item|zone", "label": "Human name"}
    ],
    "actions": [
      {"id": "ACTION_ID", "label": "Human name", "target": "ASSET_ID"}
    ],
    "containers": [
      {"id": "CONTAINER_ID", "holds": ["ASSET_ID"]}
    ],
    "states": [
      {"id": "STATE_ID", "asset": "ASSET_ID", "value": "state_value"}
    ],
    "effects": [
      {"id": "EFFECT_ID", "changes": "STATE_ID", "to": "new_value"}
    ],
    "conditions": [
      {"id": "COND_ID", "check": "STATE_ID", "equals": "expected_value"}
    ],
    "reactions": [
      {"id": "REACTION_ID", "on": "ACTION_ID", "if": "COND_ID", "trigger": "EFFECT_ID"}
    ]
  },
  "experiment": {
    "start": "STEP_ID_1",
    "steps": [
      {
        "state_id": "STEP_ID_1",
        "description": "What happens in this step",
        "wire": {
          "on": "ACTION_ID",
          "condition": "COND_ID",
          "next": "STEP_ID_2"
        }
      },
      {
        "state_id": "STEP_ID_2",
        "description": "What happens next",
        "wire": {
          "on": "ACTION_ID",
          "condition": "COND_ID",
          "next": "END"
        }
      }
    ]
  }
}

Rules:
- All IDs must be SCREAMING_SNAKE_CASE
- experiment.start must match the first step's state_id
- Every action/condition referenced in experiment must exist in registers
- Output ONLY the JSON object. Nothing else.
"""

SYSTEM_PROMPT_REFINE = """
You are GLAM — Game Logic Automation Middleware.
You will receive an existing DSL JSON and a refinement instruction.
Apply ONLY the requested change to the relevant section(s).
Keep everything else identical.
Output ONLY the full updated JSON. No markdown, no explanation, no code blocks.

Rules:
- All IDs must be SCREAMING_SNAKE_CASE
- experiment.start must match the first step's state_id
- Every action/condition referenced in experiment must exist in registers
- Output ONLY the JSON object. Nothing else.
"""


# ── JSON Syntax Highlighter ──────────────────────────────────────────────────
class JSONHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.rules = []
        key_fmt = QTextCharFormat()
        key_fmt.setForeground(QColor("#7EC8E3"))
        self.rules.append(('"[^"]*"\\s*:', key_fmt))
        str_fmt = QTextCharFormat()
        str_fmt.setForeground(QColor("#B8E0A0"))
        self.rules.append((': "([^"]*)"', str_fmt))
        num_fmt = QTextCharFormat()
        num_fmt.setForeground(QColor("#FFB347"))
        self.rules.append((r'\b\d+\.?\d*\b', num_fmt))
        bool_fmt = QTextCharFormat()
        bool_fmt.setForeground(QColor("#FF8C8C"))
        self.rules.append((r'\b(true|false|null)\b', bool_fmt))
        bracket_fmt = QTextCharFormat()
        bracket_fmt.setForeground(QColor("#555B6E"))
        self.rules.append(('[\\[\\]\\{\\}]', bracket_fmt))

    def highlightBlock(self, text):
        import re
        for pattern, fmt in self.rules:
            for match in re.finditer(pattern, text):
                self.setFormat(match.start(), match.end() - match.start(), fmt)


# ── Worker thread ────────────────────────────────────────────────────────────
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
                "prompt": self.system + "\n\n" + self.prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.3, "num_thread": 8, "num_ctx": 4096}
            }
            resp = requests.post(OLLAMA_URL, json=payload, timeout=180)
            resp.raise_for_status()
            raw = resp.json()["response"].strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()
            parsed = json.loads(raw)
            self.finished.emit(json.dumps(parsed, indent=2))
        except requests.ConnectionError:
            self.error.emit("Cannot connect to Ollama.\nRun:  ollama serve")
        except requests.Timeout:
            self.error.emit("Ollama timed out (>180s).\nTry tinyllama for faster CPU response.")
        except json.JSONDecodeError as e:
            self.error.emit(f"Model returned invalid JSON:\n{e}\n\nTry rephrasing.")
        except Exception as e:
            self.error.emit(f"Unexpected error:\n{str(e)}")


# ── Chat bubble widget ───────────────────────────────────────────────────────
class ChatBubble(QFrame):
    def __init__(self, role: str, text: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(3)

        is_user = (role == "user")

        # Role label
        role_lbl = QLabel("YOU" if is_user else "GLAM")
        role_lbl.setStyleSheet(
            f"color: {'#4F7FFF' if is_user else '#22A060'};"
            "font-size: 10px; font-weight: 700; letter-spacing: 1px;"
        )
        layout.addWidget(role_lbl)

        # Bubble
        bubble = QLabel(text)
        bubble.setWordWrap(True)
        bubble.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bubble.setStyleSheet(
            f"background: {'#1A2540' if is_user else '#162A1F'};"
            f"color: {'#A0C4FF' if is_user else '#7ECFA0'};"
            "border-radius: 8px;"
            "padding: 8px 12px;"
            "font-size: 12px;"
            "line-height: 1.5;"
        )
        layout.addWidget(bubble)

        # Timestamp
        ts = QLabel(datetime.now().strftime("%H:%M"))
        ts.setStyleSheet("color: #333A4F; font-size: 10px;")
        layout.addWidget(ts)


# ── Main Window ──────────────────────────────────────────────────────────────
class GLAMWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GLAM — Game Logic Automation Middleware")
        self.setMinimumSize(1280, 760)
        self.output_folder  = DEFAULT_OUT
        self.current_dsl    = None   # holds the live DSL dict
        self.is_first_input = True   # tracks generation vs refinement mode
        self._apply_theme()
        self._build_ui()
        self._update_input_hint()

    # ── Theme ────────────────────────────────────────────────────────────────
    def _apply_theme(self):
        self.setStyleSheet("""
        QMainWindow, QWidget {
            background-color: #0F1117;
            color: #E0E0E0;
            font-family: 'Segoe UI', sans-serif;
            font-size: 13px;
        }
        QSplitter::handle { background-color: #1E2130; width: 2px; }
        QScrollArea { border: none; background: transparent; }
        QScrollBar:vertical {
            background: #0F1117; width: 6px; border-radius: 3px;
        }
        QScrollBar::handle:vertical {
            background: #2A2D3A; border-radius: 3px; min-height: 20px;
        }
        QTextEdit {
            background-color: #161B22; color: #E0E0E0;
            border: 1px solid #2A2D3A; border-radius: 8px;
            padding: 10px;
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 12px;
            selection-background-color: #1F4068;
        }
        QLineEdit {
            background-color: #161B22; color: #E0E0E0;
            border: 1px solid #2A2D3A; border-radius: 8px;
            padding: 10px 14px; font-size: 13px;
        }
        QLineEdit:focus { border: 1px solid #4F7FFF; }
        QPushButton {
            border-radius: 8px; padding: 9px 18px;
            font-size: 13px; font-weight: 600; border: none;
        }
        QPushButton#btn_send {
            background-color: #4F7FFF; color: #FFFFFF; min-width: 80px;
        }
        QPushButton#btn_send:hover   { background-color: #6B96FF; }
        QPushButton#btn_send:disabled { background-color: #1A2540; color: #444; }
        QPushButton#btn_reset {
            background-color: #2A2D3A; color: #888; min-width: 70px;
        }
        QPushButton#btn_reset:hover { background-color: #3A2020; color: #FF8C8C; }
        QPushButton#btn_save {
            background-color: #1C7A4B; color: #FFFFFF; min-width: 120px;
        }
        QPushButton#btn_save:hover   { background-color: #22A060; }
        QPushButton#btn_save:disabled { background-color: #1A3A2A; color: #444; }
        QPushButton#btn_folder {
            background-color: #2A2D3A; color: #AAAAAA; min-width: 130px;
        }
        QPushButton#btn_folder:hover { background-color: #363A4F; color: #FFF; }
        QLabel#lbl_title {
            font-size: 20px; font-weight: 700;
            color: #4F7FFF; letter-spacing: 2px;
        }
        QLabel#lbl_sub {
            font-size: 10px; color: #333A4F; letter-spacing: 1px;
        }
        QLabel#lbl_section {
            font-size: 10px; font-weight: 700;
            color: #333A4F; letter-spacing: 1px;
        }
        QLabel#lbl_hint {
            font-size: 11px; color: #333A4F;
            padding: 2px 4px;
        }
        QFrame#divider { background-color: #1E2130; max-height: 1px; }
        QStatusBar {
            background-color: #0A0C10; color: #333A4F;
            font-size: 11px; border-top: 1px solid #1E2130;
        }
        """)

    # ── UI ───────────────────────────────────────────────────────────────────
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(20, 16, 20, 10)
        root_layout.setSpacing(12)

        # Header
        hdr = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        t = QLabel("GLAM")
        t.setObjectName("lbl_title")
        s = QLabel("GAME LOGIC AUTOMATION MIDDLEWARE")
        s.setObjectName("lbl_sub")
        title_col.addWidget(t)
        title_col.addWidget(s)
        hdr.addLayout(title_col)
        hdr.addStretch()
        badge = QLabel(f"  {MODEL}  ")
        badge.setStyleSheet(
            "background:#1A2540; color:#4F7FFF; border-radius:4px;"
            "padding:4px 8px; font-size:10px; font-weight:700;"
        )
        hdr.addWidget(badge)
        root_layout.addLayout(hdr)

        div = QFrame(); div.setObjectName("divider")
        div.setFrameShape(QFrame.HLine)
        root_layout.addWidget(div)

        # ── Main 3-column splitter ───────────────────────────────────────────
        main_split = QSplitter(Qt.Horizontal)
        main_split.setHandleWidth(2)

        # ── COL 1: Chat history ──────────────────────────────────────────────
        chat_col = QWidget()
        chat_layout = QVBoxLayout(chat_col)
        chat_layout.setContentsMargins(0, 0, 6, 0)
        chat_layout.setSpacing(6)

        lbl_chat = QLabel("CONVERSATION")
        lbl_chat.setObjectName("lbl_section")
        chat_layout.addWidget(lbl_chat)

        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.chat_inner = QWidget()
        self.chat_inner.setStyleSheet("background: transparent;")
        self.chat_inner_layout = QVBoxLayout(self.chat_inner)
        self.chat_inner_layout.setContentsMargins(4, 4, 4, 4)
        self.chat_inner_layout.setSpacing(6)
        self.chat_inner_layout.addStretch()

        self.chat_scroll.setWidget(self.chat_inner)
        chat_layout.addWidget(self.chat_scroll)

        main_split.addWidget(chat_col)

        # ── COL 2: DSL section panels ────────────────────────────────────────
        panels_col = QWidget()
        panels_layout = QVBoxLayout(panels_col)
        panels_layout.setContentsMargins(6, 0, 6, 0)
        panels_layout.setSpacing(6)

        lbl_meta = QLabel("META")
        lbl_meta.setObjectName("lbl_section")
        panels_layout.addWidget(lbl_meta)
        self.meta_view = QTextEdit()
        self.meta_view.setReadOnly(True)
        self.meta_view.setPlaceholderText("id, version, domain...")
        self.meta_view.setMaximumHeight(80)
        panels_layout.addWidget(self.meta_view)

        lbl_reg = QLabel("REGISTERS")
        lbl_reg.setObjectName("lbl_section")
        panels_layout.addWidget(lbl_reg)
        self.reg_view = QTextEdit()
        self.reg_view.setReadOnly(True)
        self.reg_view.setPlaceholderText("assets, actions, states, effects...")
        panels_layout.addWidget(self.reg_view)

        lbl_exp = QLabel("EXPERIMENT")
        lbl_exp.setObjectName("lbl_section")
        panels_layout.addWidget(lbl_exp)
        self.exp_view = QTextEdit()
        self.exp_view.setReadOnly(True)
        self.exp_view.setPlaceholderText("state machine steps...")
        self.exp_view.setMaximumHeight(130)
        panels_layout.addWidget(self.exp_view)

        main_split.addWidget(panels_col)

        # ── COL 3: Full JSON editor ──────────────────────────────────────────
        json_col = QWidget()
        json_layout = QVBoxLayout(json_col)
        json_layout.setContentsMargins(6, 0, 0, 0)
        json_layout.setSpacing(6)

        lbl_json = QLabel("FULL DSL JSON  —  editable before saving")
        lbl_json.setObjectName("lbl_section")
        json_layout.addWidget(lbl_json)

        self.json_editor = QTextEdit()
        self.json_editor.setPlaceholderText(
            "Generated DSL appears here.\nEdit freely before saving to Godot."
        )
        self.highlighter = JSONHighlighter(self.json_editor.document())
        json_layout.addWidget(self.json_editor)

        main_split.addWidget(json_col)
        main_split.setSizes([260, 320, 580])
        root_layout.addWidget(main_split, stretch=1)

        # ── Input row ────────────────────────────────────────────────────────
        input_frame = QFrame()
        input_frame.setStyleSheet(
            "background:#161B22; border-radius:10px; border:1px solid #2A2D3A;"
        )
        input_outer = QVBoxLayout(input_frame)
        input_outer.setContentsMargins(10, 8, 10, 8)
        input_outer.setSpacing(6)

        self.lbl_hint = QLabel("")
        self.lbl_hint.setObjectName("lbl_hint")
        input_outer.addWidget(self.lbl_hint)

        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        self.idea_input = QLineEdit()
        self.idea_input.setPlaceholderText(
            "Describe your game scenario to generate the DSL..."
        )
        self.idea_input.returnPressed.connect(self._on_send)
        input_row.addWidget(self.idea_input)

        self.btn_send = QPushButton("Generate")
        self.btn_send.setObjectName("btn_send")
        self.btn_send.clicked.connect(self._on_send)
        input_row.addWidget(self.btn_send)

        self.btn_reset = QPushButton("Reset")
        self.btn_reset.setObjectName("btn_reset")
        self.btn_reset.clicked.connect(self._on_reset)
        input_row.addWidget(self.btn_reset)

        input_outer.addLayout(input_row)
        root_layout.addWidget(input_frame)

        # ── Bottom save bar ──────────────────────────────────────────────────
        save_row = QHBoxLayout()
        save_row.setSpacing(10)

        self.btn_folder = QPushButton("Set Godot Folder")
        self.btn_folder.setObjectName("btn_folder")
        self.btn_folder.clicked.connect(self._on_pick_folder)
        save_row.addWidget(self.btn_folder)

        self.lbl_folder = QLabel(self.output_folder)
        self.lbl_folder.setStyleSheet("color:#333A4F; font-size:11px;")
        save_row.addWidget(self.lbl_folder, stretch=1)

        self.btn_save = QPushButton("Save to Godot")
        self.btn_save.setObjectName("btn_save")
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self._on_save)
        save_row.addWidget(self.btn_save)

        root_layout.addLayout(save_row)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Ready — describe your game idea to begin.")

    # ── Input hint label ─────────────────────────────────────────────────────
    def _update_input_hint(self):
        if self.is_first_input:
            self.lbl_hint.setText(
                "FIRST INPUT — describe the full scenario to generate a new DSL"
            )
            self.lbl_hint.setStyleSheet("color:#4F7FFF; font-size:10px; font-weight:700;")
            self.btn_send.setText("Generate")
            self.idea_input.setPlaceholderText(
                "Describe your game scenario...  e.g. 'a quest where the player rescues an NPC from a burning building'"
            )
        else:
            self.lbl_hint.setText(
                "REFINE MODE — type what to change, e.g. 'rename the NPC to Arya' or 'add a new step for collecting water'"
            )
            self.lbl_hint.setStyleSheet("color:#22A060; font-size:10px; font-weight:700;")
            self.btn_send.setText("Refine")
            self.idea_input.setPlaceholderText(
                "What should change?  e.g. 'add a condition where the door is locked first'"
            )

    # ── Send handler ─────────────────────────────────────────────────────────
    def _on_send(self):
        text = self.idea_input.text().strip()
        if not text:
            self.status.showMessage("Type something first.")
            return

        self._add_bubble("user", text)
        self.idea_input.clear()
        self.btn_send.setEnabled(False)
        self.btn_reset.setEnabled(False)

        if self.is_first_input:
            # Full generation
            prompt  = f"User idea: {text}"
            system  = SYSTEM_PROMPT_INITIAL
            self.status.showMessage("Generating full DSL...  (15–30s on CPU)")
        else:
            # Refinement — send current DSL + instruction
            current_json = self.json_editor.toPlainText().strip()
            if not current_json:
                QMessageBox.warning(self, "No DSL", "There is no DSL to refine yet.")
                self.btn_send.setEnabled(True)
                self.btn_reset.setEnabled(True)
                return
            prompt = (
                f"CURRENT DSL:\n{current_json}\n\n"
                f"REFINEMENT INSTRUCTION: {text}"
            )
            system = SYSTEM_PROMPT_REFINE
            self.status.showMessage(f"Refining DSL: '{text}'...  (15–30s on CPU)")

        self.worker = GenerateWorker(prompt, system)
        self.worker.finished.connect(lambda result: self._on_done(result, text))
        self.worker.error.connect(self._on_error)
        self.worker.start()

    # ── Done handler ─────────────────────────────────────────────────────────
    def _on_done(self, json_text: str, user_msg: str):
        self.btn_send.setEnabled(True)
        self.btn_reset.setEnabled(True)

        # Parse and update everything
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError:
            self._on_error("Model returned invalid JSON after generation.")
            return

        self.current_dsl = data
        self.json_editor.setPlainText(json_text)
        self._populate_panels(data)
        self.btn_save.setEnabled(True)

        # Build a summary for the chat bubble
        quest_id = data.get("meta", {}).get("id", "?")
        n_assets  = len(data.get("registers", {}).get("assets", []))
        n_steps   = len(data.get("experiment", {}).get("steps", []))

        if self.is_first_input:
            summary = (
                f"DSL generated.\n"
                f"id: {quest_id}\n"
                f"assets: {n_assets}   steps: {n_steps}\n"
                f"Ready to refine or save."
            )
            self.is_first_input = False
        else:
            summary = (
                f"DSL updated.\n"
                f"id: {quest_id}\n"
                f"assets: {n_assets}   steps: {n_steps}"
            )

        self._add_bubble("glam", summary)
        self._update_input_hint()
        self.status.showMessage(
            f"{'Generated' if n_steps else 'Updated'}: {quest_id}  |  "
            f"{n_assets} assets, {n_steps} steps  |  Edit JSON if needed, then Save."
        )

    def _on_error(self, msg: str):
        self.btn_send.setEnabled(True)
        self.btn_reset.setEnabled(True)
        self._add_bubble("glam", f"Error: {msg.splitlines()[0]}")
        self.status.showMessage("Error occurred — see chat.")
        QMessageBox.critical(self, "GLAM Error", msg)

    # ── Reset ────────────────────────────────────────────────────────────────
    def _on_reset(self):
        reply = QMessageBox.question(
            self, "Reset",
            "This will clear the conversation and the current DSL.\nContinue?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        self.current_dsl    = None
        self.is_first_input = True
        self._clear_chat()
        self._clear_panels()
        self.json_editor.clear()
        self.btn_save.setEnabled(False)
        self._update_input_hint()
        self.status.showMessage("Reset — enter a new idea to start fresh.")

    # ── Folder + Save ────────────────────────────────────────────────────────
    def _on_pick_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Godot quest output folder", self.output_folder
        )
        if folder:
            self.output_folder = folder
            self.lbl_folder.setText(folder)

    def _on_save(self):
        raw = self.json_editor.toPlainText().strip()
        if not raw:
            self.status.showMessage("Nothing to save.")
            return
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            QMessageBox.critical(self, "Invalid JSON", f"Fix the JSON before saving:\n{e}")
            return

        quest_id = data.get("meta", {}).get("id", "quest_unnamed")
        os.makedirs(self.output_folder, exist_ok=True)
        filepath = os.path.join(self.output_folder, f"{quest_id}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        self._add_bubble("glam", f"Saved to Godot:\n{filepath}")
        self.status.showMessage(f"Saved → {filepath}")
        QMessageBox.information(self, "Saved", f"DSL saved to:\n{filepath}")

    # ── Chat helpers ─────────────────────────────────────────────────────────
    def _add_bubble(self, role: str, text: str):
        # Insert before the trailing stretch
        stretch_item = self.chat_inner_layout.takeAt(
            self.chat_inner_layout.count() - 1
        )
        bubble = ChatBubble(role, text, self.chat_inner)
        self.chat_inner_layout.addWidget(bubble)
        self.chat_inner_layout.addStretch()

        # Scroll to bottom
        QApplication.processEvents()
        sb = self.chat_scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _clear_chat(self):
        while self.chat_inner_layout.count():
            item = self.chat_inner_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.chat_inner_layout.addStretch()

    # ── Panel population ─────────────────────────────────────────────────────
    def _populate_panels(self, data: dict):
        meta = data.get("meta", {})
        self.meta_view.setPlainText(
            f"id       :  {meta.get('id', '—')}\n"
            f"version  :  {meta.get('version', '—')}\n"
            f"domain   :  {meta.get('domain', '—')}"
        )

        reg = data.get("registers", {})
        lines = []
        for key in ["assets","actions","containers","states","effects","conditions","reactions"]:
            items = reg.get(key, [])
            ids   = ", ".join(i.get("id","?") for i in items) if items else "—"
            lines.append(f"{key:<12} [{len(items)}]  {ids}")
        self.reg_view.setPlainText("\n".join(lines))

        exp   = data.get("experiment", {})
        steps = exp.get("steps", [])
        exp_lines = [f"start  →  {exp.get('start','—')}", ""]
        for i, step in enumerate(steps):
            sid  = step.get("state_id", "?")
            desc = step.get("description", "")[:42]
            nxt  = step.get("wire", {}).get("next", "?")
            arrow = "→ END" if nxt == "END" else f"→ {nxt}"
            exp_lines += [f"[{i+1}] {sid}", f"    {desc}", f"    {arrow}", ""]
        self.exp_view.setPlainText("\n".join(exp_lines))

    def _clear_panels(self):
        self.meta_view.clear()
        self.reg_view.clear()
        self.exp_view.clear()


# ── Entry ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = GLAMWindow()
    w.show()
    sys.exit(app.exec_())