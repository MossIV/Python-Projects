import os
from dotenv import load_dotenv
import requests
import json

load_dotenv()

HOROSCOPE = os.getenv('HOROSCOPE_API_KEY')

print(HOROSCOPE)

url = "https://json.freeastrologyapi.com/western/planets"