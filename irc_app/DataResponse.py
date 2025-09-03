air = ["UAV", "BOGEY", "BANDIT", "AAV", "BANZAI" ]
# maritime =["DESTROYER", "FRIGATE","CRUISER","SUBMARINE","SUB",]
# land= ["JASSM","ATTACK"]
intel = ["RADIO", "EMISSION", "EMISSIONS","BLUR","AUTOCAT","BEAM RIDER"]
cyber = ["FORWARD LOOKUP", "REQUEST","ALLIGATOR","NETWORK","TRAFFIC"]
# friendly =["ANGELS","ANYFACE","BIRD","BITTERSWEET","BLIND","BRUISER","BULLDOG","CHICK"]

# process message
def extracted_chat(message):
    message = message.lower()

    # Finds position of the second '(' character
    first_parenthesis_pos = message.find('(')
    second_parenthesis_pos = message.find('(', first_parenthesis_pos + 1)
    
    # Extracts the message after the second '('
    if second_parenthesis_pos != -1:
        text_second_parenthesis = message[second_parenthesis_pos + 1:]  # Everything after the second '('
        
        # Split the extracted text into words
        words = text_second_parenthesis.split()  # Split into words
        first_8_words = words[:9]  # Only the first 8 words
        
        # lists 
        found_air = []
        found_intel = []
        found_cyber = []
        # found_maritime = []
        # found_land =[]

        # Check each word and categorize it
        # for word in first_8_words:
        #     if word in air:
        #         found_air.append(word)
        #     # elif word in maritime:
        #     #     found_maritime.append(word)
        #     elif word in intel:
        #         found_intel.append(word)
        #     elif word in cyber:
        #         found_cyber.append(word)

        for word in first_8_words:
            if word.lower() in [x.lower() for x in air]:  # Convert both to lowercase 
                found_air.append(word)
            # elif word.lower() in [x.lower() for x in maritime]:  
            #     found_maritime.append(word)
            elif word.lower() in [x.lower() for x in intel]:
                found_intel.append(word)
            elif word.lower() in [x.lower() for x in cyber]:
                found_cyber.append(word)

        # Return the categorized lists
        return found_air, found_intel, found_cyber, #found_maritime
    return [], [], []#, []  # If none return empty list
