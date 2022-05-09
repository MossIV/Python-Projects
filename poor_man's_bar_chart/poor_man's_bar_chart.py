"""
This script creates a bar chart of the total
occurance of letters in a sentence
"""
import pprint

sentence = input("Please type the sentence: ")

alphabet = {}

for i in sentence:
    if(i in "abcdefghijklmnopqrstuvwxyz"):
        i = i.lower()
        if(i in alphabet.keys()):
            alphabet[i].append(i)
        else:
            alphabet[i] = [i]

sorted_alphabet = dict( sorted(alphabet.items()) )

pprint.pprint(sorted_alphabet)