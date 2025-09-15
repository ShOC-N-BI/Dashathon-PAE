import re
import os
import json
import psycopg2

# To ensure that we load the words file from the directory of the script we have to do these extra steps
script_dir = os.path.dirname(__file__)
with open(os.path.join(script_dir, 'words.json'), 'r') as file:
    words = json.load(file)
    ACTIONS = words["ACTIONS"]
    WORDS = words["WORDS"]
    BATTLE_DICTIONARY = words["BATTLE DICTIONARY"]  

    # Flatten all battle dictionary keywords into a single set (lowercased for case-insensitive matching)
battle_words = set(
    word.upper()
    for category in words["BATTLE DICTIONARY"].values()
    for word in category
)
battle_lookup = {}
for category, words in BATTLE_DICTIONARY.items():
    for word in words:
        battle_lookup[word.upper()] = category
#message = "[10:48:58] WF_Clark: Analysis_Center01 (Analysis Center): @Intel_Ops (Intelligence Operations Center) 2x Torpedo 18675 were observed on EO/IR Imagery located on parking apron forward of aircraft hangers IVO 25.045310306035184, -77.464458773165 in Lane Flamingo"
#message = "[11:00:11] WF_Clark: Analysis_Center01 (Analysis Center): @Intel_Ops (Intelligence Operations Center) From 12054 to 2111Z Radio emmission were detected at location  27.689097938330395, -80.38238737940404 operating on VHF. in Lane Bellagio"
#message = "[10:45:02] WF_Clark: Floater03_OPS (USS Cole DDG): @Maritime_OPS (Maritime Operations Center) Possible helos swarm approaching from south, type unk.  Main generator still inop, drifting WNW at 5 knots, req support in Lane Ceasars"
#message = "TN:43773 Rank 1. Harpy 2. Gismo 3. Thor"
#message = "afc_watch:  SINATRA DIRECTS attack bandit cttn 14754, tot asap pls"
#message = "SINATRA DIRECTS bandit cttn 14754, tot asap pls"
#message = "@hydro_Surv miami tracks appear to be fighters possibly j-15s"

def get_db_connection():
    conn = psycopg2.connect(
        host="10.5.185.53",
        dbname="shooca_db",
        user="shooca",
        password="shooca222",
        port="5432"
    )
    return conn

# discover possible battle effectors

def action_prompt(entity, description=""):
    """
    Check and see if the entity passed can be found in the "WORDS" lists, if so then retrieve the associated "ACTIONS" and return them
    TO-DO: Review why is there a description parameter that we don't need
    """
    matched = extract_battle_effectors(message) 
    #if description:
    #    print(f"  Description: {description}")


    if matched !=[]:
        #print(f"Battle Effectors: {matched}")
        return matched, matched, matched
    else:
        i = entity.split()[0]
        for k in WORDS.keys():
            if i in WORDS[k]:
                return ACTIONS[k]
        
    return None, None, None


def get_description(words, index, max_words=4):
    # Generates a description based on the entity and the words that follow it`
    description = ""
    # Check if the word before the current entity is present and does not contain a colon or closing parenthesis
    if index > 0 and (':' not in words[index - 1] and ')' not in words[index - 1]):
        description = words[index - 1] + " "

    # Now, add the entity and additional words to the description
    for i in range(1, max_words + 1):
        if index + i < len(words):
            description += words[index + i] + " "

    return description.strip()

def tracking_number_information(tracking_number):

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # Fetch information based on the tracking number
        try:
            cur.execute("SELECT * FROM bc3_with_all_vw WHERE tracknumber = %s", (tracking_number,))
          
        except Exception as e:
            print("Tracking number not found in the database.")
        result = cur.fetchone()
        # If no results are found in the tracknumber query, try the bc3_jtn query
        if result is None:
            try:
                cur.execute("SELECT * FROM bc3_with_all_vw WHERE bc3_jtn = %s", (tracking_number,))
                result = cur.fetchone()
            except Exception as e:
                print("Tracking number not found in the database.")
                return "Tracking number not found in the database."
        cur.close()
        conn.close()

        if result:
            call_sign = result[13]
            type_of_entity = result[7] 
            frnd_or_foe = result[8]
            aircraft_type = result[18]
            latty = result[1]
            longy = result[2]
            return call_sign,type_of_entity, frnd_or_foe, aircraft_type, latty, longy        
    except Exception as e:
        
        return None, None, None, None, None, None

def extract_five_digit_numbers(text):
        # looks for 5 digit tracking numbers in the message 
        pattern = r'\b(?:tn:?|TN:?|cttn:?|CTTN:?|tn?|TN?|)[\s-]*?(\d{5})\b'
        return re.findall(pattern, text)

def match_entity(filtered_s, words, index, category_lists, message):
    # discover possible entity and actions
    for label, category in BATTLE_DICTIONARY.items():
        if filtered_s.upper() in category:
            print(f"Match found {filtered_s}")
            print(f"Battle Effect is: {label}")
            tracking_number = extract_five_digit_numbers(message)
            # CRITERIA 1 if tracking number and battle effect is found, then return that.
            if tracking_number:
                c_s,t_o_e,f_o_f,a_t, latty, longy = tracking_number_information(tracking_number[0])
                entity = ", ".join(tracking_number) + f" (CallSign: {c_s}, Track Cat: {t_o_e}, Track ID: {f_o_f}, Aircraft Type: {a_t}, Lattitude: {latty}, Longitude: {longy})"
                actions = label, label, label 
                print(f'Confirmed tracking number - {tracking_number} and Battle Effect - {label}')
            #CRITERIA 3 entity and battle effect is found, then return that.
            else:
                description = get_description(words, index)
                print(f"description: {description}")
                # entity = filtered_s + " " + description
                entity = extract_entity_in_message(words)
                print(f"entity: {entity}")
                actions =  label, label, label
                print(f'Confirmed entity - {entity} and Battle Effect - {label}')
                extracted_entity = extract_entity_in_message(words) 
                entity = " ".join(extracted_entity)+ " (" + description + ")"
            
            print("actions:")
            print(f"1. {actions[0]}")
            print(f"1. {actions[1]}")
            print(f"1. {actions[2]}")
            return entity, *actions[:3]
    return None, None, None, None


def extract_entity_in_message(words):
    print("   EXTRACTING IN MESSAGE")
    print(words)
    for i in words:
        for label, category in WORDS.items():
                i = i.rstrip('s')
                i = i.upper()
                if i in category:
                    print(f"{i} is {label}")
                    return i, label
    return None, None

def extract_battle_effectors(message):
    # Extracts words from text that match entries in the battle dictionary.
    # Returns a list of matched keywords.

    # Normalize the input text to lowercase and tokenize using regex to catch words and phrases
    good_words = re.findall(r'\b\w[\w\-]*\b', message.upper())
    matched = []
    matched_cleaned = []
    # Check for single-word matches
    for word in good_words:
        if word in battle_lookup:
            matched.append(battle_lookup[word])
            matched_cleaned = ''.join(matched)
        return matched_cleaned 
    


def extracted_chat(message):
    # Extracts entity and actions from the message.
    # Convert message to uppercase for case-insensitive matching
    message_upper = message.upper()

    # Find the first occurrence of a parenthesis and colon
    first_parenthesis_pos = message_upper.find(')')
    second_parenthesis_pos = message_upper.find(')', first_parenthesis_pos + 1)
    second_colon_pos = message_upper.find(':', message_upper.find(':') + 1)

    # Determine the starting position for text extraction
    if second_colon_pos != -1:
        start_pos = second_colon_pos + 1
    else:
        start_pos = second_parenthesis_pos + 1 if second_parenthesis_pos != -1 else 0

    # Extract the text after the first parenthesis or colon
    text_to_process = message[start_pos:].strip()
    # create list of words from the text
    words = text_to_process.split()


    for i, word in enumerate(words):
        # filters out any characters that are not alphanumeric or hyphens, joins the remaining characters into a new string
        filtered_word = ''.join(e for e in word if e.isalnum() or e == '-').upper()
        # remove all trailing 'S' from the filtered word (possibly remove in the future)
        filtered_s = filtered_word.rstrip('S')
        # Check if the filtered word is in the words dictionary
        print(f"Working on word: {filtered_s} --------------------")
        final_entity, act1, act2, act3 = match_entity(filtered_s,words, i, WORDS, message,)
        print(f"End on work: {filtered_s} -----------------------")
        if final_entity != None:
           print(f"result true")
           return final_entity, act1, act2, act3       
        else:
           print(f"Result false")
    return None, None, None, None




# filtered_s, action1, action2, action3 = extracted_chat(message)
# print(f"Entity: {filtered_s}")
# print(f"Action 1: {action1}")
# print(f"Action 2: {action2}")
# print(f"Action 3: {action3}")
