# GLAM — Game Logic Automation Middleware

GLAM is a local AI-powered pipeline that converts natural language game ideas into structured DSL (JSON) and injects them into a Godot game for execution.

---

## 🧠 What This Project Does

This system allows you to:

1. Describe a game scenario in plain English
2. Generate a structured **DSL (Domain Specific Language)** using a local AI model (Ollama)
3. Save the DSL as a JSON file
4. Automatically load and execute that logic inside a Godot project

---

## 🏗️ Architecture Overview

```
[User Input]
      ↓
[Python UI (PyQt5)]
      ↓
[Ollama (Local LLM)]
      ↓
[Generated DSL JSON]
      ↓
[Saved to Godot /data/quests]
      ↓
[Godot GLAM System]
      ↓
[Game State Machine Execution]
```

---

## ⚙️ Core Components

### 1. Python UI (`glam_ui.py`)



* Built using **PyQt5**
* Provides:

  * Chat interface (Generate + Refine mode)
  * JSON viewer + editor
  * Save-to-Godot functionality
* Uses **Ollama API (`localhost:11434`)** to generate DSL

---

### 2. DSL Structure

The generated JSON contains:

#### Meta

* id, version, domain

#### Registers

Defines reusable components:

* assets (objects, NPCs, items)
* actions (player interactions)
* states (world state)
* effects (state changes)
* conditions (checks)
* reactions (event logic)

#### Experiment (State Machine)

* Step-based flow system
* Each step:

  * description
  * action trigger
  * condition
  * next step

---

### 3. Godot Integration

Godot reads DSL JSON from:

```
res://data/quests/
```

Main scripts:

* `GLAMLoader.gd` → Loads JSON
* `RegisterManager.gd` → Stores logic definitions
* `ExperimentRunner.gd` → Runs state machine
* `GLAMSystem.gd` → Main controller

---

## 🚀 How It Works

### Step 1 — Run Ollama

```bash
ollama serve
ollama pull mistral
```

---

### Step 2 — Run Python UI

```bash
pip install PyQt5 requests
python glam_ui.py
```

---

### Step 3 — Generate DSL

* Enter a game idea
* Click **Generate**
* Refine using follow-up instructions
* Click **Save to Godot**

This creates:

```
data/quests/<quest_id>.json
```

---

### Step 4 — Run Godot

* Open project

* Ensure scene contains:

  ```
  GLAMSystem
  ├── GLAMLoader
  ├── RegisterManager
  └── ExperimentRunner
  ```

* Press ▶ Play

---

## 🎮 Example Output

```
GLAM: Loaded → test1
GLAM Registers loaded — assets: 4 actions: 3 reactions: 2
GLAM Experiment started at: IDLE
=== Step: IDLE ===
    Child harvests the grown crop
```

---

## 🧪 Triggering Actions

From any script in Godot:

```gdscript
get_node("/root/GLAMSystem").do_action("ACTION_ID")
```

---

## ⚡ Requirements

* Python 3.10+
* PyQt5
* requests
* Ollama (local LLM)
* Godot 4.x

---

## 🖥️ Notes

* Works on CPU-only systems (recommended model: `phi3:mini`)
* Generation time: ~10–30 seconds
* JSON is editable before saving

---

## 💡 Future Improvements

* Visual UI for game state
* NPC dialogue integration
* Real-time action triggers
* Multiplayer logic generation

---

## 🧑‍💻 Author

Built as part of an experimental AI-driven game pipeline system.

---
