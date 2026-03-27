{
  "meta": {
    "id": "chem_lab_v1",
    "version": "1.0",
    "domain": "chemistry",
    "difficulty": "primary"
  },

  "registries": {

    "assets": {
      "items": [
        "vinegar",
        "baking_soda",
        "water",
        "indicator",
        "salt"
      ],
      "containers": [
        "beaker"
      ],
      "tools": [
        "burner",
        "stirrer"
      ]
    },

    "actions": {
      "add": ["item", "target"],
      "mix": ["target"],
      "heat": ["target"],
      "stir": ["target"],
      "observe": ["target"]
    },

    "containers": {
      "beaker": {
        "capacity": 3,
        "allowed_items": [
          "vinegar",
          "baking_soda",
          "water",
          "indicator",
          "salt"
        ],
        "can_mix": true,
        "can_heat": true
      }
    },

    "states": {
      "beaker": [
        "empty",
        "filled",
        "mixed",
        "heated",
        "reaction_complete",
        "overflow"
      ],
      "liquid": [
        "normal",
        "heated",
        "evaporated",
        "colored"
      ]
    },

    "effects": {
      "bubbles": { "type": "particle", "duration": 3 },
      "foam": { "type": "particle", "duration": 4 },
      "steam": { "type": "particle", "duration": 5 },
      "color_change": { "type": "visual" },
      "dissolve": { "type": "visual" },
      "overflow": { "type": "animation" }
    },

    "conditions": [
      "step_completed",
      "contains_item",
      "is_heated",
      "sequence_match"
    ],

    "reactions": [
      {
        "id": "foam_reaction",
        "inputs": ["vinegar", "baking_soda"],
        "conditions": [],
        "output": {
          "effects": ["bubbles", "foam"],
          "state_change": {
            "target": "beaker",
            "value": "reaction_complete"
          }
        }
      }
    ],

    "mascot": {
      "id": "chem_bot",
      "name": "ChemBot",
      "style": "friendly",
      "role": "guide"
    }
  },

  "experiment": {
    "id": "foam_reaction_experiment",
    "start_step": 1,

    "steps": [

      {
        "step_id": 1,
        "action": "add",
        "target": "beaker",
        "required": { "item": "vinegar" },
        "conditions": [],
        "narration": "Let's start by adding vinegar into the beaker!",
        "hint": "Click on vinegar and pour it into the beaker.",
        "on_complete": [
          "state:add:beaker:vinegar"
        ],
        "next_step": 2
      },

      {
        "step_id": 2,
        "action": "add",
        "target": "beaker",
        "required": { "item": "baking_soda" },
        "conditions": ["step_1_completed"],
        "narration": "Now add baking soda. Something exciting is about to happen!",
        "hint": "Try selecting baking soda and adding it to the same beaker.",
        "on_complete": [
          "state:add:beaker:baking_soda"
        ],
        "next_step": 3
      },

      {
        "step_id": 3,
        "action": "mix",
        "target": "beaker",
        "conditions": ["step_1_completed", "step_2_completed"],
        "narration": "Mix the contents and observe the reaction!",
        "hint": "Use the mix option on the beaker.",
        "on_complete": [
          "trigger_reaction:beaker"
        ],
        "next_step": null
      }
    ]
  }
}