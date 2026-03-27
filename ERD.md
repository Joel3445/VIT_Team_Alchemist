SYSTEM
│
├── 🧑 Player
│    └── performs → Action
│
├── ⚙️ Action System
│    ├── add(item, container)
│    ├── mix(container)
│    ├── heat(container)
│    ├── stir(container)
│    └── observe(container)
│
│    RELATIONS:
│    ├── uses → Item
│    ├── targets → Container
│    └── uses → Tool (optional)
│
├── 🧱 Entity (Base Class)
│    ├── id
│    ├── type → [item | container | tool | mascot]
│    ├── subtype → depends on type
│    ├── state → depends on subtype
│    └── properties → dynamic attributes
│
│
├── 🧪 Item (inherits Entity)
│    ├── subtype → [liquid | powder]
│    ├── name → vinegar, water, salt, etc.
│    ├── state
│    │    ├── liquid → [normal, heated, colored, evaporated]
│    │    └── powder → [normal, dissolved]
│    └── properties
│         ├── color
│         ├── temperature
│         └── reactive (true/false)
│
│
├── 🧱 Container (inherits Entity)
│    ├── subtype → [beaker]
│    ├── contents → List<Item>
│    ├── capacity → integer
│    ├── state
│    │    ├── empty
│    │    ├── filled
│    │    ├── mixed
│    │    ├── heated
│    │    ├── reaction_complete
│    │    └── overflow
│    └── capabilities
│         ├── can_mix → true/false
│         └── can_heat → true/false
│
│    RELATION:
│    └── contains → Item[]
│
│
├── 🛠️ Tool (inherits Entity)
│    ├── subtype → [burner | stirrer | dropper]
│    ├── state
│    │    ├── burner → [on, off]
│    │    └── others → idle
│    └── function
│         ├── burner → heats container
│         ├── stirrer → mixes container
│         └── dropper → controlled addition
│
│    RELATION:
│    └── modifies → Container
│
│
├── 🤖 Mascot (inherits Entity)
│    ├── id → chem_bot
│    ├── name → ChemBot
│    ├── style → friendly
│    ├── role → guide
│    └── functions
│         ├── narration
│         ├── hint
│         └── feedback
│
│    RELATION:
│    └── narrates → Step
│
│
├── 🧠 State System
│    ├── applied_to → Entity (Item / Container)
│    ├── depends_on → subtype
│    └── updated_by → Action / Reaction
│
│
├── 🧪 Reaction System
│    ├── inputs → Item[]
│    ├── conditions → [state, heat, steps]
│    ├── target → Container
│    └── output
│         ├── effects → Effect[]
│         └── state_change → Container.state
│
│    RELATION:
│    └── reads → Container.contents
│         → triggers → Effect + State update
│
│
├── ✨ Effect System
│    ├── type → [particle | visual | animation]
│    ├── applied_to → Container
│    └── triggered_by → Reaction
│
│
├── 🔁 Step Engine (DSL Execution)
│    ├── step_id
│    ├── action → Action
│    ├── target → Entity
│    ├── required → Item
│    ├── conditions → [step_completed, state]
│    ├── narration → Mascot
│    ├── hint → Mascot
│    ├── on_complete
│    │    ├── state update
│    │    └── trigger reaction
│    └── next_step → step_id
│
│    RELATION:
│    └── controls → Action execution flow
│
│
└── 🔄 SYSTEM FLOW

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