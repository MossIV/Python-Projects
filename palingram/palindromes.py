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
palindromesB = []


def findPalindromes():
    palindromes = []
    for i in wordList:
        if ((len(i)>1) & (i == i[::-1])):
            palindromes.append(i)
    pprint.pprint(palindromes)

def isPalindrome(word):
    if len(word) in (0,1):
        return True;
    elif (word[0] == word[len(word)-1]):
        word = word[1:len(word)-1]
        return(isPalindrome(word))
    else:
        return False

def findPalingrams():
    palingrams = []
    words = set(wordList)
    for i in words:
        end = len(i)
        rev_word = i[::-1]

        if end > 1:
            for j in range(end):
                if (i[j:] == rev_word[:end-j]) & (rev_word[end-j:] in words):
                    palingrams.append((i,rev_word[end-j:]))
                if (i[j:] == rev_word[end-j:]) & (rev_word[:end-j] in words):
                    palingrams.append((rev_word[:end-j],i))
    return palingrams

for i in wordList:
    if (i in 'abcdefghijklmnopqrstuvwxyz'):
        wordList.remove(i);

for i in wordList:
    if(isPalindrome(i)):
        palindromesB.append(i)
pprint.pprint(palindromesB)

sorted_palingrams = sorted(findPalingrams())

# pprint.pprint(sorted_palingrams)