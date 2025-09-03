import re

air_enemy = ["UAV", "BOGEY", "BANDIT", "BANZAI",
    "BANDIT", "BOGEY", "BOGEY DOPE", "BLOW THROUGH", "BLOODHOUND", "BRACKET", 
    "BREAK (DIRECTION)", "BREAKAWAY", "BINGO", "BREVITY", "BRUISER", "BUGOUT", "BUSTER", "MIG-21", "MIG-15", "MIG-17", "MIG-19", "MIG-23", "MIG-25", "MIG-29", "MIG-31",
    "SU-7", "SU-9", "SU-11", "SU-15", "SU-17", "SU-20", "SU-22", "SU-24", "SU-25",
    "SU-27", "SU-30", "SU-33", "SU-35", "SU-57", "YAK-9", "YAK-23", "YAK-25", "YAK-28",
    "YAK-38", "YAK-41", "J-16", "J-50", "J-36", "J-35", "J-20", "J-15", "J-16", "J-10B", "J-11B", "J-10", "FC-1", 
    "JH-7", "Su-30MK2", "Su-30MKK", "Su-35S", "J-11D", "J-13", "J-12", "J-11", "J-9", 
    "J-8", "J-7", "J-6", "J-5", "J-2", "MiG-9", "Su-27", "Q-5", "Q-6", "J-16D", "J-15D", 
    "H-20", "H-8", "H-7", "H-6", "H-5", "Tu-14", "Tu-2", "KJ-600", "KJ-500", "KJ-2000", 
    "Y-9JZ ELINT", "Y-8CB", "Y-8DZ", "Y-8G", "Y-8GX3", "Y-8JB", "Y-8T", "Y-8W", "Y-8EW", 
    "ZDK03", "Y-8J", "KJ-200", "Y-7", "KJ-1 AEWC", "An-30", "CIOMP", 
    "YY-20", "HY-6", "Il-78", "JZ-8", "JZ-7", "MIG-29", "MIG-31", "MIG-35", "SU-27", "SU-30", "SU-34", "SU-35", "SU-57", 
    "SU-24", "SU-25", "MI-8", "MI-24", "MI-28", "KA-52", "KA-60", "ANSAT", 
    "PANTHER", "IL-76", "IL-78", "IL-112", "IL-214", "AN-26", "AN-72", 
    "BE-200", "TU-22M", "TU-160", "TU-95", "B-2", "S-400", "T-50", "T-14", 
    "AWACS", "AIRCRAFT", "HELICOPTER", "HELO", "BOMBER", "BOMBERS", "FIGHTER", "FIGHTERS", "A/C", "AIRCRAFTS",
    "MIG21", "MIG15", "MIG17", "MIG19", "MIG23", "MIG25", "MIG29", "MIG31",
    "SU7", "SU9", "SU11", "SU15", "SU17", "SU20", "SU22", "SU24", "SU25",
    "SU27", "SU30", "SU33", "SU35", "SU57", "YAK9", "YAK23", "YAK25", "YAK28",
    "YAK38", "YAK41", "J16", "J50", "J36", "J35", "J20", "J15", "J16", "J10B", "J11B", "J10", "FC1", 
    "JH7", "Su30MK2", "Su30MKK", "Su35S", "J11D", "J13", "J12", "J11", "J9", 
    "J8", "J7", "J6", "J5", "J2", "MiG9", "Su27", "Q5", "Q6", "J16D", "J15D", 
    "H20", "H8", "H7", "H6", "H5", "Tu14", "Tu2", "KJ600", "KJ500", "KJ2000", 
    "Y9JZ ELINT", "Y8CB", "Y8DZ", "Y8G", "Y8GX3", "Y8JB", "Y8T", "Y8W", "Y8EW", 
    "ZDK03", "Y8J", "KJ200", "Y7", "KJ1 AEWC", "An30",
    "YY20", "HY6", "Il78", "JZ8", "JZ7", "MIG29", "MIG31", "MIG35", "SU27", "SU30", "SU34", "SU35", "SU57", 
    "SU24", "SU25", "MI8", "MI24", "MI28", "KA52", "KA60", "IL76", "IL78", "IL112", "IL214", "AN26", "AN72", 
    "BE200", "TU22M", "TU160", "TU95", "B2", "S400", "T50", "T14"
]

surface = ["DESTROYER", "DD", "FRIGATE", "FF", "CRUISER", "CC", "SUBMARINE", "SUB", 
    "CARRIER", "CV", "BANZAI", "BRACKET", "BUMP/BUMP-UP", "BURN-GLINT", "BUSTER", 
    "BLANK", "BULLDOG", "BREVITY", "BANDIT", "BOGEY", "BASSETT", "BRUISER", "COBRA", 
    "COWBOYS", "CYCLOPS", "DEADEYE", "JASSM", "ATTACK", "AAV", "DDG", "CVN", "CG", 
    "LHD", "LPD", "LCS", "SSN", "SSBN", "LHA", "T-AKE", "AOR", "LST", "T-AO", "FFG", 
    "RADAR", "VESSEL", "SHIP", "BB", "CA", "SSGN", "LSD", "AO", "AE", "AK", "AR", "PC", 
    "PY", "MCM", "MSC", "AIRCRAFT-CARRIER", "NUCLEAR-POWERED-AIRCRAFT-CARRIER", "BATTLESHIP", 
    "HEAVY-CRUISER", "GUIDED-MISSILE-CRUISER", "DESTROYER", "GUIDED-MISSILE-DESTROYER", 
    "FRIGATE", "GUIDED-MISSILE-FRIGATE", "SUBMARINE-(DIESEL-ELECTRIC)", 
    "NUCLEAR-POWERED-SUBMARINE-(ATTACK)", "NUCLEAR-POWERED-BALLISTIC-MISSILE-SUBMARINE", 
    "NUCLEAR-POWERED-GUIDED-MISSILE-SUBMARINE", "AMPHIBIOUS-ASSAULT-SHIP", 
    "AMPHIBIOUS-ASSAULT-SHIP-(DIFFERENT-CONFIGURATION)", "AMPHIBIOUS-TRANSPORT-DOCK", 
    "LANDING-SHIP-TANK", "DOCK-LANDING-SHIP", "FLEET-OILER", "AMMUNITION-SHIP", 
    "CARGO-SHIP", "REPAIR-SHIP", "PATROL-CRAFT", "PATROL-YACHT", 
    "MINE-COUNTERMEASURES-SHIP", "MINESWEEPER-COMMAND-SHIP"

]
Incoming = ["MISSILE", "ROCKET", "TORPEDO", "BOMB", "TORP", "CRUISE", "BALLISTIC","LAUNCHED", "LAUNCH", "FIRE", "ENGAGED",
             "ANTI-SHIP MISSILE", "ASW", "AAM", "AGM", "A/S", "A/G", "A/A", "A/T", "A/D", "A/P", "A/L",
               "SURFACE-TO-AIR", "CRUISE-MISSILE","CRUISE",
    "BALLISTIC-MISSILE",
    "ANTI-SHIP-MISSILE",
    "ANTI-AIR-MISSILE",
    "AIR-TO-GROUND-MISSILE",
    "SURFACE-TO-AIR-MISSILE",
    "SURFACE-TO-SURFACE-MISSILE",
    "LAND-ATTACK-CRUISE-MISSILE",
    "SUBMARINE-LAUNCHED-CRUISE-MISSILE",
    "SUBMARINE-LAUNCHED-BALLISTIC-MISSILE",
    "SUBMARINE-LAUNCHED-ANTI-SHIP-MISSILE",
    "SUBMARINE-LAUNCHED-LAND-ATTACK-CRUISE-MISSILE"
    "SUBMARINE-LAUNCHED-ANTI-AIR-MISSILE"
    ]

intel = ["RADIO", "EMISSION", "EMISSIONS", "BLUR", "AUTOCAT", "BEAM RIDER","CTTN","RADAR","NOISE","SIGNAL","JAMMING"]

cyber = ["FORWARD LOOKUP", "REQUEST", "ALLIGATOR", "NETWORK", "TRAFFIC"]

civilian = [
    "CIVILIAN", "CIV", "NON-COMBATANT", "NON-HOSTILE", "HUMANITARIAN", "REFUGEE", "CIVILIAN-AREA", "HUMANITARIAN-MISSION", "COMMERCIAL", "COMMERCIAL-VESSEL", "COMMERCIAL-PLANE", "COMMERCIAL A/C"
]
enem = ["ENEMY", "HOSTILE", "THREAT", "TARGET","ADVERSARY", "OPFOR", "OPPOSITION", "FOE", "RIVAL", "AGGRESSOR", "ANTAGONIST", "BANDIT", "BOGEY"]

rando = ["RANDOM", "UNKNOWN", "UNK", "UNIDENTIFIED", "UNCONFIRMED", "UNCERTAIN", "POTENTIAL"]
out =["SWIM","BEER"]

battle_effect_dict = {
    "Attack":["Attack, Intercept", "Ambush", "Assail", "Assault", "Strike", "Hit", "Raid", "Invade", "Advance", "Shoot", "Suppress", "Disable"],
    "Investigate":["Investigate", "Consider", "Examine", "Explore", "Inspect", "Interrogate", "Probe", "Question", "Review", "Search", "Study", "Inquire", "Research", "Faded", "Fade", "Shadow"],
    "Communicate":["Communicate", "Broadcast", "Contact", "Convey", "Correspond", "Disclose", "Reach out", "Pass On", "Tell", "Transfer", "Transmit", "Discover", "Relay", "Report"],
    "Destroy":["Destroy", "Kill", "Nullify", "Terminate", "Vanish"],
    "Counter":["Counter", "Hinder", "Counteract", "Oppose", "Respond", "Retaliate"],
    "Evade":["Evade", "Avoid", "Circumvent", "Conceal", "Elude", "Escape", "Fend Off", "Flee", "Hide"],
    "Brace for Impact": ["Brace for Impact", "Prepare", "Fortify"],
    "Jam":["Jam", "Block", "Bind", "Congest"],
    "Hack":["Hack"],
    "Counter":["Counter", "Hinder", "Counteract", "Oppose", "Respond", "Retaliate"],
    "Psyop":["Psyop", "Propaganda"],
    "Harass":["Harass", "Hassle", "Intimidate", "Torment", "Disturb"]
}

# message = "[10:48:58] WF_Clark: Analysis_Center01 (Analysis Center): @Intel_Ops (Intelligence Operations Center) 2x Torpedo were observed on EO/IR Imagery located on parking apron forward of aircraft hangers IVO 25.045310306035184, -77.464458773165 in Lane Flamingo"
# message = "[11:00:11] WF_Clark: Analysis_Center01 (Analysis Center): @Intel_Ops (Intelligence Operations Center) From 1205Z to 2111Z Radio emmission were detected at location  27.689097938330395, -80.38238737940404 operating on VHF. in Lane Bellagio"
# message = "[10:45:02] WF_Clark: Floater03_OPS (USS Cole DDG): @Maritime_OPS (Maritime Operations Center) Possible helos swarm approaching from south, type unk.  Main generator still inop, drifting WNW at 5 knots, req support in Lane Ceasars"
# message = "[10:48:58] WF_Clark: Analysis_Center01 (Analysis Center): @Intel_Ops (Intelligence Operations Center) 2x J-16s were observed on EO/IR Imagery located on parking apron forward of aircraft hangers IVO 25.045310306035184, -77.464458773165 in Lane Flamingo"
#message = "[11:22:33] WF_FYST: IntelOps: @ Hydro_MSO, TN 44993/94/95/96 are all 1x J-15 each track."
# def get_description(words, index, max_words=5):
#     description = ' '.join(words[index+1:index+max_words]) if index + max_words <= len(words) else ' '.join(words[index+1:])

def action_prompt(entity, description=""):
    if description:
        print(f"  Description: {description}")

    for i in entity.split():
        if i in air_enemy:
            actions = ["Attack", "Investigate", "Communicate", "Destroy"]
        elif i in Incoming:
            actions = ["Counter", "Evade", "Brace for impact"]
        elif i in surface:
            actions = ["Attack", "Investigate", "Communicate"]
        elif i in intel:
            actions = ["Jam", "Communicate", "Investigate"]
        elif i in cyber:
            actions = ["Jam", "Hack", "Counter"]
        elif i in civilian:
            actions = ["Monitor", "Investigate", "Communicate"]
        elif i in rando:
            actions = ["Monitor", "Investigate", "Communicate"]
        elif i in enem:
            actions = ["Attack","Psyop","Harass"]
        else:
            actions = None, None, None
        break
    return actions

def get_description(words, index, max_words=4):
    description = ""
    # Check if the word before the current entity is present and does not contain a colon or closing parenthesis
    if index > 0 and (':' not in words[index - 1] and ')' not in words[index - 1]):
        description = words[index - 1] + " "

    # Now, add the entity and additional words to the description
    for i in range(1, max_words + 1):
        if index + i < len(words):
            description += words[index + i] + " "

    return description.strip()

def extracted_chat(message):
    message_upper = message.upper()
    
    # Find the positions of the second parenthesis ')'
    first_parenthesis_pos = message_upper.find(')')
    second_parenthesis_pos = message_upper.find(')', first_parenthesis_pos + 1)
    
    # Find the second colon ':'
    second_colon_pos = message_upper.find(':', message_upper.find(':') + 1)
    
    # If a second colon is found, start from that position
    if second_colon_pos != -1:
        start_pos = second_colon_pos + 1
    else:
        start_pos = second_parenthesis_pos + 1 if second_parenthesis_pos != -1 else 0  # Fallback to second parenthesis position if no second colon
    
    # Extract the message text starting from the found position (after second colon or second parenthesis)
    text_to_process = message[start_pos:].strip()
    
    words = text_to_process.split()

    found_air = []
    found_intel = []
    found_cyber = []
    found_surface = []
    found_civilian = []
    found_defend = []
    found_rando = []
    found_enemy =[]

    for i, word in enumerate(words):
        filtered_word = ''.join(e for e in word if e.isalnum() or e == '-').upper()
        filtered_s = filtered_word.rstrip('S')

        if filtered_s in air_enemy:
            found_air.append(filtered_s)
            description = get_description(words, i)
            filtered_s = filtered_s + " " + description
            actions = action_prompt(filtered_s)
            action1, action2, action3 = actions[:3]
            return filtered_s, action1, action2, action3

        if filtered_s in Incoming:
            found_defend.append(filtered_s)
            description = get_description(words, i)
            filtered_s = filtered_s + " " + description
            actions = action_prompt(filtered_s)
            action1, action2, action3 = actions[:3]
            return filtered_s, action1, action2, action3

        elif filtered_s in surface:
            found_surface.append(filtered_s)
            description = get_description(words, i)
            filtered_s = filtered_s + " " + description
            actions = action_prompt(filtered_s)
            action1, action2, action3 = actions[:3]
            return filtered_s, action1, action2, action3

        elif filtered_s in intel:
            found_intel.append(filtered_s)
            description = get_description(words, i)
            filtered_s = filtered_s + " " + description
            actions = action_prompt(filtered_s)
            action1, action2, action3 = actions[:3]
            return filtered_s, action1, action2, action3

        elif filtered_s in cyber:
            found_cyber.append(filtered_s)
            description = get_description(words, i)
            filtered_s = filtered_s + " " + description
            actions = action_prompt(filtered_s)
            action1, action2, action3 = actions[:3]
            return filtered_s, action1, action2, action3

        elif filtered_s in civilian:
            found_civilian.append(filtered_s)
            description = get_description(words, i)
            filtered_s = filtered_s + " " + description
            actions = action_prompt(filtered_s)
            action1, action2, action3 = actions[:3]
            return filtered_s, action1, action2, action3
        
        elif filtered_s in rando:
            found_rando.append(filtered_s)
            description = get_description(words, i)
            filtered_s = filtered_s + " " + description
            actions = action_prompt(filtered_s)
            action1, action2, action3 = actions[:3]
            return filtered_s, action1, action2, action3
        
        elif filtered_s in enem:
            found_enemy.append(filtered_s)
            description = get_description(words, i)
            filtered_s = filtered_s + " " + description
            actions = action_prompt(filtered_s)
            action1, action2, action3 = actions[:3]
            return filtered_s, action1, action2, action3

    
    return None, None, None, None

# filtered_s, action1, action2, action3 = extracted_chat(message)
# print(f"Entity: {filtered_s}")
# print(f"Action 1: {action1}")
# print(f"Action 2: {action2}")
# print(f"Action 3: {action3}")
