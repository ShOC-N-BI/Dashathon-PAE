import os
import sys

# Necissary to import files from the parent directory
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

# Load the functions that we are going to test
# TO-DO: make the load of the functions be dynamic.
from EntGen import extracted_chat, action_prompt

# Load Json containing all of our test cases
import json
cases = None
file_path = 'cases.json'
with open(file_path, 'r') as file:
    cases = json.load(file)

if cases is None:
    raise Exception("Error loading case file, unable to find test cases.")


errors_found = 0
for f_to_test in cases.keys():
    for case in cases[f_to_test]:
        error = []
        expected = case["expected"]
        #     A fairly naive way of converting the array from the json into tuples, so we can pass them to our function.
        # This won't work if we are using named parameters, but should be fine for the moment.
        func = getattr(__import__('sys').modules[__name__], f_to_test)
        results = func(*tuple(case["parameters"]))
        for e in expected:
            if (e not in results):
                error.append(f"Error, unexpected result '{e}'")
        for r in results:
            if (r not in expected):
                error.append(f"Error, missing result '{r}'")

        if len(error) != 0:
            errors_found += len(error)
            print(f"Errors ({len(error)}) found in function 'extracted_chat ({'\n\t,'.join(case['parameters'])})': \n\t\t{'\n\t\t'.join(error)}")



if errors_found != 0:
    raise Exception(f"\nFound {errors_found} errors when testing project, please review the errors and fix.")
else:
    print(f"Success, no errors found")