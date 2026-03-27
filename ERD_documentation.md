## 🧠 System Architecture & Entity Relationship Document

---

## 1. 🎯 Overview

This system models an **interactive chemistry simulation engine** driven by a structured DSL (Domain-Specific Language).
It ensures:

* Deterministic execution
* Registry-based validation
* Step-controlled interaction flow
* Modular and scalable design

---

## 2. 🧱 Core Architecture

The system is built around:

```text
Entity → Action → State → Reaction → Effect → Step Engine
```

---

## 3. 🌳 Entity Hierarchy

### 🔹 Base Entity

All objects inherit from a common structure:

```text
Entity
├── id
├── type → item | container | tool | mascot
├── subtype → depends on type
├── state → depends on subtype
└── properties → dynamic attributes
```

---

## 4. 🧪 Item System

```text
Item (type = item)
├── subtype → liquid | powder
├── name → vinegar, water, salt
├── state
│   ├── liquid → normal, heated, colored, evaporated
│   └── powder → normal, dissolved
└── properties
    ├── color
    ├── temperature
    └── reactive (boolean)
```

---

## 5. 🧱 Container System

```text
Container (type = container)
├── subtype → beaker
├── contents → List<Item>
├── capacity → integer
├── state
│   ├── empty
│   ├── filled
│   ├── mixed
│   ├── heated
│   ├── reaction_complete
│   └── overflow
└── capabilities
    ├── can_mix
    └── can_heat
```

### 🔗 Relationship

```text
Container → contains → Item[]
```

---

## 6. 🛠️ Tool System

```text
Tool (type = tool)
├── subtype → burner | stirrer | dropper
├── state
│   ├── burner → on/off
│   └── others → idle
└── function
    ├── burner → heats container
    ├── stirrer → mixes container
    └── dropper → controlled addition
```

### 🔗 Relationship

```text
Tool → modifies → Container
```

---

## 7. 🤖 Mascot System

```text
Mascot (type = mascot)
├── id → chem_bot
├── name → ChemBot
├── style → friendly
├── role → guide
└── functions
    ├── narration
    ├── hint
    └── feedback
```

### 🔗 Relationship

```text
Mascot → narrates → Step
```

---

## 8. ⚙️ Action System

```text
Action
├── type → add | mix | heat | stir | observe
├── actor → player
├── target → Entity
└── input → Item (optional)
```

### 🔗 Action Relationships

```text
add:
  Item → Container

mix:
  Container → state change

heat:
  Tool (burner) → Container

stir:
  Tool (stirrer) → Container
```

---

## 9. 🧠 State System

```text
State
├── applied_to → Entity (Item / Container)
├── depends_on → subtype
└── updated_by → Action / Reaction
```

---

## 10. 🧪 Reaction System

```text
Reaction
├── inputs → Item[]
├── conditions → state / heat / steps
├── target → Container
└── output
    ├── effects → Effect[]
    └── state_change → Container.state
```

### 🔗 Relationship

```text
Reaction reads → Container.contents
         → triggers → Effect + State update
```

---

## 11. ✨ Effect System

```text
Effect
├── type → particle | visual | animation
├── applied_to → Container
└── triggered_by → Reaction
```

---

## 12. 🔁 Step Engine (DSL Execution)

```text
Step
├── step_id
├── action → Action
├── target → Entity
├── required → Item
├── conditions → step/state conditions
├── narration → Mascot
├── hint → Mascot
├── on_complete
│   ├── state update
│   └── trigger reaction
└── next_step → step_id
```

### 🔗 Relationship

```text
Step Engine → controls → Action flow
```

---

## 13. 🔄 System Execution Flow

```text
Player
  ↓
Select Item
  ↓
Perform Action
  ↓
Target Container
  ↓
Update Container.contents
  ↓
Step Engine validates
  ↓
Reaction Engine checks
  ↓
Reaction triggered
  ↓
Effect applied
  ↓
State updated
  ↓
Mascot narrates
```

---

## 14. 🧠 Design Principles

* ✅ **Registry-driven validation** — no undefined entities
* ✅ **Deterministic execution** — step-controlled flow
* ✅ **Modular architecture** — scalable and extendable
* ✅ **Separation of concerns** — logic, visuals, and narration decoupled

---

## 15. 🚀 Summary

This system represents a:

> **Structured simulation engine that converts predefined logic into interactive, guided learning experiences using a deterministic DSL.**

---

