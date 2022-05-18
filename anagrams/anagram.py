""" This script finds anagrams of the word typed by a user from the dictionary"""

import sys

def load(file):
    """Open a text file & return a list of lowercase strings."""
    try:
        with open(file, encoding="utf-8") as in_file:
            loaded_txt = in_file.read().strip().split('\n')
            loaded_txt = [x.lower() for x in loaded_txt]
            return loaded_txt
    except IOError as error:
        print(f"{error}\nError opening {file}. Terminating program", file=sys.stderr)
        sys.exit(1)

wordList = load('words.txt')

user_word = input("Please type your word here: ")

anagrams = []

sorted_word = sorted(user_word.lower())

for word in wordList:
    word = word.lower()
    if user_word != word:
        if sorted(word) == sorted_word:
            anagrams.append(word)

print("Anagrams =", *anagrams, sep='\n')
