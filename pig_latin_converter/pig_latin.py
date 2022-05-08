"""
This script takes a word as input and uses indexing and 
slicing to return its Pig Latin equivalent.
"""

while True:
    word = input("type in an english word: ")
    if (word[0] in {'a','e','i','o','u'}):
        new_word = word + "way"
    else:
        new_word = word[1:] + word[0:1] + "ay"

    print(f"The pig latin word of {word} is {new_word}")
    
    