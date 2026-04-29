[
  {
    "id": "pae-002",
    "requestId": "0101-12 d",
    "label": "Imminent Ballistic Missile Launch",
    "description": "Multiple sensors have detected preparations for a TBM Type 1 launch from a known enemy site (Target PB1.2).",
    "gbcId": None,
    "entitiesOfInterest": [
      "TGT-TBM-001"
    ],
    "battleEntity": [
      "TBM Type 1"
    ],
    "battleEffects": [
      {
        "id": "pae-002-e01",
        "effectOperator": "Destroy",
        "description": "Strike the launch bunker entrance pre-emptively with precision-guided munitions.",
        "timeWindow": "Pre-emptive",
        "stateHypothesis": "The launch facility will be destroyed, preventing the missile from being launched.",
        "opsLimits": [
          {
            "description": "Target coordinates must be CAT 1.",
            "battleEntity": "Stealth Bomber",
            "stateHypothesis": "Assumes the TBM is still on the ground at the time of impact."
          }
        ],
        "goalContributions": [
          {
            "battleGoal": "2.1.c",
            "effect": "high"
          }
        ],
        "recommended": True,
        "ranking": 1
      },
      {
        "id": "pae-002-e02",
        "effectOperator": "Intercept",
        "description": "Intercept the incoming ballistic missile post-launch using a ballistic missile defense system.",
        "timeWindow": "Boost/Midcourse Phase",
        "stateHypothesis": "The enemy ballistic missile will be destroyed before reaching its intended target.",
        "opsLimits": [
          {
            "description": "BMD system must have a clear track and be within engagement range.",
            "battleEntity": "BMD System",
            "stateHypothesis": "Requires cueing from upstream sensors for initial track."
          }
        ],
        "goalContributions": [
          {
            "battleGoal": "2.2.a",
            "effect": "high"
          }
        ],
        "recommended": False,
        "ranking": 2
      },
      {
        "id": "pae-002-e03",
        "effectOperator": "Suppress",
        "description": "Disrupt the command-and-control communications link for the TBM launch sequence.",
        "timeWindow": "Immediate",
        "stateHypothesis": "The enemy's ability to issue the final launch command will be disrupted.",
        "opsLimits": [
          {
            "description": "Jamming asset must be on station and targeting the correct frequency range.",
            "battleEntity": "Electronic Attack Aircraft",
            "stateHypothesis": "Assumes launch sequence is dependent on a remote C2 link."
          }
        ],
        "goalContributions": [
          {
            "battleGoal": "2.1.c",
            "effect": "medium"
          }
        ],
        "recommended": False,
        "ranking": 3
      }
    ],
    "chat": [
      "AMTI SAT has detected activity consistent with TBM launch preparations at PB1.2.",
      "PAE generated for pre-emptive and defensive options."
    ],
    "isDone": False,
    "originator": "AFRL",
    "lastUpdated": "2026-04-20T17:41:10.264328+00:00"
  }
]
 