import json
import requests
from fastapi import FastAPI
import fastapi
from pydantic import BaseModel
import uvicorn
import os
import signal
import logging
from collections import defaultdict

DEBUG = True
PORT = 10500
USER_NAME = "EvanH"

hand = []
discard = []
cannot_discard = ""

game_history = []
opponent_moves = defaultdict(int)

app = FastAPI()

def load_learning_data():
    try:
        with open("learning_data.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"discard_tendencies": {}, "opponent_patterns": {}}

learning_data = load_learning_data()

def save_learning_data():
    with open("learning_data.json", "w") as f:
        json.dump(learning_data, f)

def update_game_history(move):
    game_history.append(move)
    save_learning_data()

def track_opponent_move(card):
    opponent_moves[card] += 1

def choose_discard():
    discard_options = hand.copy()
    discard_options.sort(key=lambda card: opponent_moves.get(card, 0))
    chosen_discard = discard_options[0]
    learning_data["discard_tendencies"].setdefault(chosen_discard, 0)
    learning_data["discard_tendencies"][chosen_discard] += 1
    return chosen_discard

@app.get("/")
async def root():
    return {"status": "Running"}

class GameInfo(BaseModel):
    game_id: str
    opponent: str
    hand: str

@app.post("/start-2p-game/")
async def start_game(game_info: GameInfo):
    global hand, discard
    hand = game_info.hand.split(" ")
    hand.sort()
    logging.info("2p game started, hand is " + str(hand))
    return {"status": "OK"}

class HandInfo(BaseModel):
    hand: str

@app.post("/start-2p-hand/")
async def start_hand(hand_info: HandInfo):
    global hand, discard
    discard = []
    hand = hand_info.hand.split(" ")
    hand.sort()
    logging.info("2p hand started, hand is " + str(hand))
    return {"status": "OK"}

def process_events(event_text):
    global hand, discard
    for event_line in event_text.splitlines():
        if ((USER_NAME + " draws") in event_line or (USER_NAME + " takes") in event_line):
            hand.append(event_line.split(" ")[-1])
            hand.sort()
        if "discards" in event_line:
            discard.insert(0, event_line.split(" ")[-1])
        if "takes" in event_line:
            discard.pop(0)
        if " Ends:" in event_line:
            logging.info(event_line)

class UpdateInfo(BaseModel):
    game_id: str
    event: str

@app.post("/update-2p-game/")
async def update_2p_game(update_info: UpdateInfo):
    process_events(update_info.event)
    return {"status": "OK"}

@app.post("/draw/")
async def draw(update_info: UpdateInfo):
    global cannot_discard
    process_events(update_info.event)
    if len(discard) < 1:
        cannot_discard = ""
        return {"play": "draw stock"}
    if any(discard[0][0] in s for s in hand):
        cannot_discard = discard[0]
        return {"play": "draw discard"}
    return {"play": "draw stock"}

@app.post("/lay-down/")
async def lay_down(update_info: UpdateInfo):
    global hand, discard, cannot_discard
    process_events(update_info.event)
    discard_choice = choose_discard()
    if discard_choice in hand:
        hand.remove(discard_choice)
    logging.info("Discarding: " + discard_choice)
    return {"play": "discard " + discard_choice}

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