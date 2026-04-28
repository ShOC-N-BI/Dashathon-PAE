[
  {
    "id": # unique ID ,
    "requestId": # ID of the original message,
    "label": # concise title,
    "description": # summarize the message,
    "gbcId": null,
    "entitiesOfInterest": [
      # which keyword was detected
    ],
    "battleEntity": [
      # what is the enemy
    ],
    "battleEffects": [
      {
        "id": "pae-002-e01",
        "effectOperator": # one of three battle effects chosen from the list of available,
        "description": # summarize why that effect was chosen,
        "timeWindow": # how fast would this take place,
        "stateHypothesis": # summarize what would happen if this effect was chosen,
        "opsLimits": [
          {
            "description": "Target coordinates must be CAT 1.",
            "battleEntity": # what kind of asset can conduct this effect,
            "stateHypothesis": # any limitations that may occur
          }
        ],
        "goalContributions": [
          {
            "battleGoal": "2.1.c",
            "effect": "high"
          }
        ],
        "recommended": true,
        "ranking": 1
      },
      {
        "id": "pae-002-e02",
        "effectOperator": # one of three battle effects chosen from the list of available,
        "description": # summarize why that effect was chosen,
        "timeWindow": # how fast would this take place,
        "stateHypothesis": # summarize what would happen if this effect was chosen,
        "opsLimits": [
          {
            "description": "BMD system must have a clear track and be within engagement range.",
            "battleEntity": # what kind of asset can conduct this effect,
            "stateHypothesis": # any limitations that may occur
          }
        ],
        "goalContributions": [
          {
            "battleGoal": "2.2.a",
            "effect": "high"
          }
        ],
        "recommended": false,
        "ranking": 2
      },
      {
        "id": "pae-002-e03",
        "effectOperator": # one of three battle effects chosen from the list of available,
        "description":# summarize why that effect was chosen,
        "timeWindow": # how fast would this take place,
        "stateHypothesis": # summarize what would happen if this effect was chosen,
        "opsLimits": [
          {
            "description": "Jamming asset must be on station and targeting the correct frequency range.",
            "battleEntity": # what kind of asset can conduct this effect,
            "stateHypothesis": # any limitations that may occur
          }
        ],
        "goalContributions": [
          {
            "battleGoal": "2.1.c",
            "effect": "medium"
          }
        ],
        "recommended": false,
        "ranking": 3
      }
    ],
    "chat": [
      # the original message 
      "PAE generated for pre-emptive and defensive options."
    ],
    "isDone": false,
    "originator": # who sent this message in the chat,
    "lastUpdated": "2026-04-20T17:41:10.264328+00:00" # format for when message was received
  }
]
 