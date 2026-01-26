import json

with open("scripts/riftbound_cards.json", "r") as file:
    cards = json.load(file)

print(len(cards))
