"""
This script creates a bar chart of the total
occurance of all letters in the alphabet so that a
comparison of a another latin-based writing system
can be made
"""
import pprint

sentence = input("Please type the sentence: ")

alphabet = {}

for i in "abcdefghijklmnopqrstuvwxyz":
    alphabet[i] = []

for i in sentence:
    if i in "abcdefghijklmnopqrstuvwxyz":
        i = i.lower()
        alphabet[i].append(i)

# sorted_alphabet = dict( sorted(alphabet.items()) )

pprint.pprint(alphabet)
