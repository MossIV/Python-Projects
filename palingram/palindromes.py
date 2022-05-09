"""
This script finds palingrams inside an assorted list
"""

import sys
import pprint

def load(file):
    """Open a text file & return a list of lowercase strings."""
    try:
        with open(file) as in_file:
            loaded_txt = in_file.read().strip().split('\n')
            loaded_txt = [x.lower() for x in loaded_txt]
            return loaded_txt 
    except IOError as e:
        print(f"{e}\nError opening {file}. Terminating program", file=sys.stderr)
        sys.exit(1)

wordList = load("palingram\words.txt")
palindromes = []

for i in wordList:
    if ((len(i)>1) & (i == i[::-1])):
        palindromes.append(i)

pprint.pprint(palindromes)