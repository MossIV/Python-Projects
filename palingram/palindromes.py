"""
This script finds palingrams inside an assorted list
"""

import sys
import pprint

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

wordList = load(r"palingram\words.txt")
palindromesB = []


def find_palindromes():
    """
    finds palindromes within a wordlist
    """
    palindromes = []
    for j in wordList:
        if (len(j)>1) & (j == j[::-1]):
            palindromes.append(j)
    pprint.pprint(palindromes)

def is_palindrome(word):
    """
    find palindromes recursively from a wordlist
    """
    if len(word) in (0,1):
        return True
    if word[0] == word[len(word)-1]:
        word = word[1:len(word)-1]
        return is_palindrome(word)
    return False

def find_palingrams():
    """
    finding 2 word palingrams
    """
    palingrams = []
    words = set(wordList)
    for k in words:
        end = len(k)
        rev_word = k[::-1]

        if end > 1:
            for j in range(end):
                if (k[j:] == rev_word[:end-j]) & (rev_word[end-j:] in words):
                    palingrams.append((k,rev_word[end-j:]))
                if (k[j:] == rev_word[end-j:]) & (rev_word[:end-j] in words):
                    palingrams.append((rev_word[:end-j],k))
    return palingrams

for i in wordList:
    if i in 'abcdefghijklmnopqrstuvwxyz':
        wordList.remove(i)

for i in wordList:
    if is_palindrome(i):
        palindromesB.append(i)
pprint.pprint(palindromesB)

sorted_palingrams = sorted(find_palingrams())

# pprint.pprint(sorted_palingrams)
