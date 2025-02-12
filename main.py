import requests
from fastapi import FastAPI
import fastapi
from pydantic import BaseModel
import uvicorn
import os
import signal
import logging
from collections import defaultdict

"""
By Evan Hanson, Revision 1.4
Written for Hardin-Simmons CSCI-4332 Artificial Intelligence
Revision History
1.0 - API setup
1.1 - Very basic test player
1.2 - Bugs fixed and player improved, should no longer forfeit
1.3 - Added simple learning mechanism
1.4 - Learning now focuses on draw decisions and meldable cards
"""

DEBUG = True
PORT = 10500
USER_NAME = "EvanH"

hand = []  # list of cards in our hand
discard = []  # list of cards organized as a stack
cannot_discard = ""
draw_history = []  # Tracks draw decisions and their outcomes
meldable_counts = defaultdict(int)  # Tracks meldable cards after each draw

# Define data classes for API endpoints
class GameInfo(BaseModel):
    game_id: str
    opponent: str
    hand: str

class HandInfo(BaseModel):
    hand: str

class UpdateInfo(BaseModel):
    game_id: str
    event: str

# Create the FastAPI application
app = FastAPI()

# Define routes
@app.get("/")
async def root():
    return {"status": "Running"}

@app.post("/start-2p-game/")
async def start_game(game_info: GameInfo):
    global hand, discard, draw_history
    hand = game_info.hand.split(" ")
    hand.sort()
    draw_history = []  # Reset draw history for new game
    logging.info("2p game started, hand is " + str(hand))
    return {"status": "OK"}

@app.post("/start-2p-hand/")
async def start_hand(hand_info: HandInfo):
    global hand, discard, draw_history
    discard = []
    hand = hand_info.hand.split(" ")
    hand.sort()
    draw_history = []  # Reset draw history for new hand
    logging.info("2p hand started, hand is " + str(hand))
    return {"status": "OK"}

def process_events(event_text):
    global hand, discard
    for event_line in event_text.splitlines():
        if ((USER_NAME + " draws") in event_line or (USER_NAME + " takes") in event_line):
            card = event_line.split(" ")[-1]
            hand.append(card)
            hand.sort()
            logging.info("Drew a " + card + ", hand is now: " + str(hand))
        if "discards" in event_line:
            discard.insert(0, event_line.split(" ")[-1])
        if "takes" in event_line:
            discard.pop(0)
        if " Ends:" in event_line:
            evaluate_draw_outcomes()

def evaluate_draw_outcomes():
    """Evaluate the impact of draw decisions on meldable cards."""
    global draw_history, meldable_counts
    if not draw_history:
        return

    # Calculate the number of meldable cards in the current hand
    current_meldable = calculate_meldable_cards(hand)

    # Update the meldable_counts based on the last draw decision
    last_draw = draw_history[-1]
    meldable_counts[last_draw] += current_meldable

def calculate_meldable_cards(hand):
    """Calculate the number of meldable cards in the hand."""
    if not hand:
        return 0

    # Count the number of cards that can form melds (e.g., pairs, runs)
    meldable = 0
    card_counts = defaultdict(int)
    for card in hand:
        card_counts[card[0]] += 1

    for count in card_counts.values():
        if count >= 2:  # At least a pair
            meldable += count

    return meldable

def get_of_a_kind_count(hand):
    """Calculate the number of cards of the same rank in the hand."""
    if not hand:
        return [0, 0, 0, 0]  # No cards in hand

    # Count the number of 1 of a kind, 2 of a kind, etc.
    of_a_kind_count = [0, 0, 0, 0]  # [1 of a kind, 2 of a kind, 3 of a kind, 4 of a kind]
    card_counts = defaultdict(int)
    for card in hand:
        card_counts[card[0]] += 1

    for count in card_counts.values():
        if count >= 1 and count <= 4:
            of_a_kind_count[count - 1] += 1

    return of_a_kind_count

def get_count(hand, card):
    """Count how many cards of the same rank as `card` are in the hand."""
    return sum(1 for c in hand if c[0] == card[0])

@app.post("/update-2p-game/")
async def update_2p_game(update_info: UpdateInfo):
    process_events(update_info.event)
    return {"status": "OK"}

@app.post("/draw/")
async def draw(update_info: UpdateInfo):
    global cannot_discard, draw_history
    process_events(update_info.event)

    # Decide whether to draw from discard or stock based on learning
    if len(discard) < 1:
        cannot_discard = ""
        draw_history.append("stock")
        return {"play": "draw stock"}

    # Use learning to decide: prefer the draw type with higher meldable counts
    if meldable_counts["discard"] > meldable_counts["stock"] and any(discard[0][0] in s for s in hand):
        cannot_discard = discard[0]
        draw_history.append("discard")
        return {"play": "draw discard"}

    draw_history.append("stock")
    return {"play": "draw stock"}

@app.post("/lay-down/")
async def lay_down(update_info: UpdateInfo):
    global hand, discard, cannot_discard
    process_events(update_info.event)
    of_a_kind_count = get_of_a_kind_count(hand)
    if (of_a_kind_count[0] + (of_a_kind_count[1] * 2)) > 1:
        if of_a_kind_count[0] > 0:
            for i in range(len(hand) - 1, -1, -1):
                # Handle edge cases for first and last card
                if i == 0:
                    if len(hand) > 1 and hand[i][0] != hand[i + 1][0]:
                        return {"play": "discard " + hand.pop(i)}
                elif i == len(hand) - 1:
                    if hand[i][0] != hand[i - 1][0]:
                        return {"play": "discard " + hand.pop(i)}
                else:
                    if hand[i][0] != hand[i - 1][0] and hand[i][0] != hand[i + 1][0]:
                        return {"play": "discard " + hand.pop(i)}
        elif of_a_kind_count[1] >= 1:
            for i in range(len(hand) - 1, -1, -1):
                if hand[i] != cannot_discard and get_count(hand, hand[i]) == 2:
                    return {"play": "discard " + hand.pop(i)}
            return {"play": "discard " + hand.pop(i)}

    discard_string = ""
    if of_a_kind_count[0] > 0:
        if hand[-1][0] != hand[-2][0]:
            discard_string = " discard " + hand.pop()
        else:
            for i in range(len(hand) - 2, -1, -1):
                if i == 0:
                    if len(hand) > 1 and hand[i][0] != hand[i + 1][0]:
                        discard_string = " discard " + hand.pop(i)
                        break
                elif i == len(hand) - 1:
                    if hand[i][0] != hand[i - 1][0]:
                        discard_string = " discard " + hand.pop(i)
                        break
                else:
                    if hand[i][0] != hand[i - 1][0] and hand[i][0] != hand[i + 1][0]:
                        discard_string = " discard " + hand.pop(i)
                        break

    play_string = ""
    last_card = ""
    while len(hand) > 0:
        card = hand.pop(0)
        if str(card)[0] != last_card:
            play_string += "meld "
        play_string += str(card) + " "
        last_card = str(card)[0]

    play_string = play_string[:-1] + discard_string
    logging.info("Playing: " + play_string)
    return {"play": play_string}

@app.get("/shutdown")
async def shutdown_API():
    os.kill(os.getpid(), signal.SIGTERM)
    logging.info("Player client shutting down...")
    return fastapi.Response(status_code=200, content='Server shutting down...')

if __name__ == "__main__":
    if DEBUG:
        url = "http://127.0.0.1:16200/test"
        logging.basicConfig(filename="RummyPlayer.log", format='%(asctime)s - %(levelname)s - %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S', level=logging.INFO)
    else:
        url = "http://127.0.0.1:16200/register"
        logging.basicConfig(filename="RummyPlayer.log", format='%(asctime)s - %(levelname)s - %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S', level=logging.WARNING)

    payload = {
        "name": USER_NAME,
        "address": "127.0.0.1",
        "port": str(PORT)
    }

    try:
        response = requests.post(url, json=payload)
    except Exception as e:
        print("Failed to connect to server. Please contact Mr. Dole.")
        exit(1)

    if response.status_code == 200:
        print("Request succeeded.")
        print("Response:", response.json())
    else:
        print("Request failed with status:", response.status_code)
        print("Response:", response.text)
        exit(1)

    uvicorn.run(app, host="127.0.0.1", port=PORT)