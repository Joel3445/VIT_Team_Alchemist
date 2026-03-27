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
        "salt",
        "sugar"
      ],
      "containers": [
        "beaker"
      ],
      "tools": [
        "burner",
        "stirrer",
        "dropper"
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
          "salt",
          "sugar"
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
      "bubbles": {
        "type": "particle",
        "duration": 3
      },
      "foam": {
        "type": "particle",
        "duration": 4
      },
      "steam": {
        "type": "particle",
        "duration": 5
      },
      "color_change": {
        "type": "visual"
      },
      "dissolve": {
        "type": "visual"
      },
      "overflow": {
        "type": "animation"
      }
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
        "inputs": [
          "vinegar",
          "baking_soda"
        ],
        "conditions": [],
        "output": {
          "effects": [
            "bubbles",
            "foam"
          ],
          "state_change": {
            "target": "beaker",
            "value": "reaction_complete"
          }
        }
      },
      {
        "id": "heating_water",
        "inputs": [
          "water"
        ],
        "conditions": [
          "is_heated"
        ],
        "output": {
          "effects": [
            "steam"
          ],
          "state_change": {
            "target": "beaker",
            "value": "heated"
          }
        }
      },
      {
        "id": "indicator_reaction",
        "inputs": [
          "indicator",
          "vinegar"
        ],
        "conditions": [],
        "output": {
          "effects": [
            "color_change"
          ],
          "state_change": {
            "target": "beaker",
            "value": "colored"
          }
        }
      },
      {
        "id": "dissolve_salt",
        "inputs": [
          "water",
          "salt"
        ],
        "conditions": [],
        "output": {
          "effects": [
            "dissolve"
          ],
          "state_change": {
            "target": "beaker",
            "value": "mixed"
          }
        }
      },
      {
        "id": "overflow_reaction",
        "inputs": [
          "vinegar",
          "baking_soda"
        ],
        "conditions": [
          "is_heated"
        ],
        "output": {
          "effects": [
            "foam",
            "overflow"
          ],
          "state_change": {
            "target": "beaker",
            "value": "overflow"
          }
        }
      }
    ]
  },

  "experiment": {
    "id": "foam_reaction_experiment",
    "start_step": 1,

    "steps": [

      {
        "step_id": 1,
        "action": "add",
        "target": "beaker",
        "required": {
          "item": "vinegar"
        },
        "conditions": [],
        "on_complete": [
          "state:add:beaker:vinegar"
        ],
        "next_step": 2
      },

      {
        "step_id": 2,
        "action": "add",
        "target": "beaker",
        "required": {
          "item": "baking_soda"
        },
        "conditions": [
          "step_1_completed"
        ],
        "on_complete": [
          "state:add:beaker:baking_soda"
        ],
        "next_step": 3
      },

      {
        "step_id": 3,
        "action": "mix",
        "target": "beaker",
        "conditions": [
          "step_1_completed",
          "step_2_completed"
        ],
        "on_complete": [
          "trigger_reaction:beaker"
        ],
        "next_step": null
      }
    ]
  }
}