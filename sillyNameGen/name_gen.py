"""
This script generates a random name from the two list of fisrt, middle and last names
"""
import random

print("Welcome to the League 'Sidekick Name Picker. ' \n")
print("A name just like Batman would pick for Robin: \n\n")

first = ('Baby Oil', 'Bad News', 'Big Burps', "Bill", "Bob",
'Bowel Noises', 'Boxelder', "Bud", 'Butterbean', 'Buttermilk',
 'Buttocks', 'Chad', 'Chesterfield', 'Chewy', 'Chigger', 'Cinnabuns',
  'Cleet', 'Cornbread', 'Crab Meat', 'Crapps', 'Dark Skies',
   'Dennis Clawhammer', 'Dicman', 'Elphonso', 'Fancypants',
    'Figgs', 'Foncy', 'Gootsy', 'Greasy Jim', 'Huckleberry',
     'Huggy', 'Ignatious', 'Jimbo', "Joe 'Pottin Soil'",
      'Johnny', 'Lemongrass', 'Lil Debil', 'Longbranch',
       '"Lunch Money"', 'Mergatroid', 'Mr Peabody',
         'Oinks', 'Old Scratch', 'Ovaltine',
         'Pennywhistle', 'Pitchfork Ben', 'Potato Bug',
          'Pushmeet', 'Rock Candy', 'Schlomo', 'Scratchensniff',
           'Scut', "Sid", 'Skidmark', 'Slaps',
            'Snakes', 'Snoobs', 'Snorki', 'Soupcan Sam', 'Spitzitout',
             'Squids', 'Stinky', 'Storyboard', 'Sweet Tea', 'TeeTee',
              'Wheezy Joe',"Winston 'Jazz Hands'", 'Worms')

middle = ('Jingley', 'Sugar','stinkbug','Beenie-Weenie',
'The Squirts','Oil-Can','The Big News','Grunt','Twinkle',
'Winkie','Lite')

last = ('Appleyard', 'Bigmeat', 'Bloominshine', 'Boogerbottom', 'Breedslovetrout',
 'Butterbaugh', 'Clovenhoof', 'Clutterbuck', 'Cocktoasten', 'Endicott',
  'Fewhairs', 'Gooberdapple', 'Goodensmith', 'Goodpasture', 'Guster',
   'Henderson', 'Hooperbag', 'Hoosenater', 'Hootkins', 'Jefferson',
    'Jenkins', 'Schmidt', 'Johnson', 'Kingfish', 'Listenbee',
     "M'Bembo", 'McFadden', 'Moonshine', 'Nettles', 'Noseworthy',
      'Olivetti', 'Outerbridge', 'Overpeck', 'Overturf', 'Oxhandler',
       'Pealike', 'Pennywhistle', 'Peterson', 'Pieplow', 'Pinkerton',
        'Porkins', 'Putney', 'Quakenbush', 'Rainwater', 'Rosenthal',
         'Rubbins', 'Sackrider', 'Snuggleshine', 'Splern', 'Stevens',
          'Stroganoff', 'Gold', 'Swackhamer', 'Tippins', 'Turnipseed',
           'Vinaigrette', 'Walkingstick', 'Wallbanger', 'Weewax', 'Weiners',
            'Whipkey', 'Wigglesworth', 'Wimplesnatch', 'Winterkorn',
        'Woolysocks')

while True:
    firstName = random.choice(first)
    lastName = random.choice(last)
    middleName = random.choice(middle)

    print("\n\n")
    if random.random() > 0.666:
        print(f"\033[1;31;40m{firstName} {middleName} {lastName}")
    else:
        print(f"\033[1;31;40m{firstName} {lastName}")
    print("\033[0;37;40m\n\n")

    tryAgain = input("\n\n Try again? (Press Enter else n to quit)\n ")
    if tryAgain.lower() == "n":
        break

input("\nPress Enter to exit.")
