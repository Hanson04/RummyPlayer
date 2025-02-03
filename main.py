import requests
from fastapi import FastAPI, Response
import fastapi
from pydantic import BaseModel
import uvicorn
import os
import signal
import logging
import random  # for exploration in our learning routines

"""
By Evan Hanson, Revision 1.1
Revised by ChatGPT to add a simple learning mechanism for a rummy card player.
This version records moves and then, upon detecting game-end outcomes,
updates win/loss statistics for each type of move. In future turns the player
will favor actions with better historical performance.
"""

DEBUG = True
PORT = 10500
USER_NAME = "EvanH"

# Rummy game state
hand = []  # list of cards in our hand
discard = []  # list of cards organized as a stack

# ------------------------
# Learning globals
# ------------------------
# Record the moves we take during the game.
# Each element is a tuple: (move_type, action)
# move_type is "draw" or "discard"
move_history = []

# Simple statistics: for the two draw actions we keep win/loss counts.
draw_stats = {
    "draw discard": {"wins": 0, "losses": 0},
    "draw stock": {"wins": 0, "losses": 0}
}

# For discards we will record statistics per card (or card rank).
discard_stats = {}  # keys will be card strings; values: {"wins": int, "losses": int}

# Exploration probability (epsilon-greedy)
epsilon = 0.1

# ------------------------
# Set up the FastAPI application
# ------------------------
app = FastAPI()


# Root endpoint
@app.get("/")
async def root():
    ''' Root API simply confirms API is up and running. '''
    return {"status": "Running"}


# Data class for start-of-game info
class GameInfo(BaseModel):
    game_id: str
    opponent: str
    hand: str


@app.post("/start-2p-game/")
async def start_game(game_info: GameInfo):
    ''' Game Server calls this endpoint to inform player a new game is starting. '''
    global hand, discard
    hand = game_info.hand.split(" ")
    hand.sort()
    discard = []
    logging.info("2p game started, hand is " + str(hand))
    return {"status": "OK"}


# Data class for start-of-hand info
class HandInfo(BaseModel):
    hand: str


@app.post("/start-2p-hand/")
async def start_hand(hand_info: HandInfo):
    ''' Game Server calls this endpoint to inform player a new hand is starting, continuing the previous game. '''
    global hand, discard
    # Note: sort() returns None; so we split then sort in two steps
    hand = hand_info.hand.split(" ")
    hand.sort()
    logging.info("2p hand started, hand is " + str(hand))
    return {"status": "OK"}


def process_events(event_text):
    ''' Shared function to process event text from various API endpoints. '''
    global hand, discard
    for event_line in event_text.splitlines():
        # If the event says we drew or took a card, update our hand.
        if ((USER_NAME + " draws") in event_line or (USER_NAME + " takes") in event_line):
            card = event_line.split(" ")[-1]
            logging.info("Event: Drew card " + card)
            hand.append(card)
            hand.sort()
        # If someone discards, add the card to the discard pile.
        if ("discards" in event_line):
            card = event_line.split(" ")[-1]
            discard.insert(0, card)
        # If someone takes from the discard pile, remove the top card.
        if ("takes" in event_line):
            if discard:
                discard.pop(0)


# Data class for update info
class UpdateInfo(BaseModel):
    game_id: str
    event: str


@app.post("/update-2p-game/")
async def update_2p_game(update_info: UpdateInfo):
    '''
    Game Server calls this endpoint to update player on game status and other players' moves.
    Typically only called at the end of game.
    '''
    global move_history, draw_stats, discard_stats
    process_events(update_info.event)

    # Look for game-end outcome in the event text.
    outcome = None
    low_event = update_info.event.lower()
    if "win" in low_event:
        outcome = "win"
    elif "loss" in low_event or "lose" in low_event:
        outcome = "loss"

    # If we detected an outcome, update our learning statistics.
    if outcome is not None:
        reward = 1 if outcome == "win" else -1
        logging.info("Game outcome detected: {} (reward {})".format(outcome, reward))
        # Update draw move stats.
        for move in move_history:
            move_type, action = move
            if move_type == "draw":
                if reward > 0:
                    draw_stats[action]["wins"] += 1
                else:
                    draw_stats[action]["losses"] += 1
            elif move_type == "discard":
                # Update stats for the discarded card.
                if action not in discard_stats:
                    discard_stats[action] = {"wins": 0, "losses": 0}
                if reward > 0:
                    discard_stats[action]["wins"] += 1
                else:
                    discard_stats[action]["losses"] += 1
        # Clear move history for next game.
        move_history.clear()

    return {"status": "OK"}


@app.post("/draw/")
async def draw(update_info: UpdateInfo):
    '''
    Game Server calls this endpoint to start player's turn with a draw from discard pile or draw pile.
    We now use a simple learned strategy combined with a heuristic.
    '''
    global hand, discard, move_history, draw_stats, epsilon

    process_events(update_info.event)

    # Only one valid option if the discard pile is empty.
    if len(discard) < 1:
        chosen_action = "draw stock"
        move_history.append(("draw", chosen_action))
        logging.info("Discard pile empty; choosing to " + chosen_action)
        return {"play": chosen_action}

    # The two valid actions are:
    #   "draw stock" and "draw discard"
    valid_actions = ["draw stock", "draw discard"]

    # Epsilon-greedy: sometimes choose a random action.
    if random.random() < epsilon:
        chosen_action = random.choice(valid_actions)
        logging.info("Exploration: randomly chose " + chosen_action)
    else:
        # Use our learned stats if available.
        # Compute win ratios for each action (avoid division by zero)
        ratio_stock = draw_stats["draw stock"]["wins"] / (
                    draw_stats["draw stock"]["wins"] + draw_stats["draw stock"]["losses"] + 1e-5)
        ratio_discard = draw_stats["draw discard"]["wins"] / (
                    draw_stats["draw discard"]["wins"] + draw_stats["draw discard"]["losses"] + 1e-5)
        # Also compute a simple heuristic: if our hand already contains a card matching the top discard’s rank,
        # we lean toward drawing the discard.
        heuristic = "draw discard" if any(discard[0][0] in card for card in hand) else "draw stock"

        # Choose based on a combination: if the heuristic move has a better win ratio (or is the only one with data), choose it.
        if heuristic == "draw discard":
            chosen_action = "draw discard" if ratio_discard >= ratio_stock else "draw stock"
        else:
            chosen_action = "draw stock" if ratio_stock >= ratio_discard else "draw discard"
        logging.info(
            "Based on learned stats: draw stock ratio=%.3f, draw discard ratio=%.3f; heuristic suggests %s; chosen %s" %
            (ratio_stock, ratio_discard, heuristic, chosen_action))

    # Record our move for later learning.
    move_history.append(("draw", chosen_action))
    return {"play": chosen_action}


@app.post("/lay-down/")
async def lay_down(update_info: UpdateInfo):
    '''
    Game Server calls this endpoint to conclude player's turn with melding and/or discard.
    Here we generate melds as before, but when discarding we choose a card based on learned discard stats.
    '''
    global hand, discard, move_history, discard_stats

    process_events(update_info.event)

    # First, we try to analyze our hand.
    # The original code created counts of cards of a kind.
    of_a_kind_count = [0, 0, 0, 0]  # counts for singles, pairs, triplets, etc.
    last_val = hand[0][0]
    count = 0
    for card in hand[1:]:
        cur_val = card[0]
        if cur_val == last_val:
            count += 1
        else:
            of_a_kind_count[count] += 1
            count = 0
        last_val = cur_val
    if count != 0:
        of_a_kind_count[count] += 1

    # If there are too many unmeldable cards (heuristic),
    # we need to discard one.
    candidate_discard = None
    if (of_a_kind_count[0] + of_a_kind_count[1]) > 1:
        # Instead of simply choosing the highest card that is a one-of-a-kind,
        # we scan through the hand and choose one that has (or is assumed to have) the best
        # win ratio in our discard stats. We assume that if we have little data for a card,
        # its ratio defaults to 0.5.
        best_ratio = -1.0
        # We look at each card in hand (we iterate over a copy since we may remove one)
        for card in hand:
            # Use the card string as the key; if no stats exist, assume 0.5.
            stats = discard_stats.get(card, {"wins": 0, "losses": 0})
            ratio = stats["wins"] / (stats["wins"] + stats["losses"] + 1e-5)
            # In this simple scheme, a higher ratio means that discarding that card has been associated with wins.
            # (You might wish to reverse the logic if you believe that “bad” cards are ones that hurt your chances.)
            if ratio > best_ratio:
                best_ratio = ratio
                candidate_discard = card

        # Fallback: if for some reason we did not select one, choose the highest card.
        if candidate_discard is None:
            candidate_discard = hand[-1]

        # Remove the candidate card from hand.
        hand.remove(candidate_discard)
        logging.info("Discarding candidate card: " + candidate_discard)
        # Record this discard move for learning.
        move_history.append(("discard", candidate_discard))
    else:
        # If we are in a good meldable state, follow the original heuristic: discard the highest unmeldable card.
        # (This is the original approach from the example code.)
        for i in range(len(hand) - 1, -1, -1):
            if i == 0 or hand[i][0] != hand[i - 1][0]:
                candidate_discard = hand.pop(i)
                logging.info("Discarding (heuristic) " + candidate_discard)
                move_history.append(("discard", candidate_discard))
                break

    # Now, generate our meld play.
    play_string = ""
    last_card = ""
    # Meld out the rest of the hand.
    while len(hand) > 0:
        card = hand.pop(0)
        if card != last_card:
            play_string += "meld "
        play_string += str(card) + " "
        last_card = card

    # Append the discard move.
    play_string = play_string.strip() + " discard " + candidate_discard
    logging.info("Playing: " + play_string)
    return {"play": play_string}


@app.get("/shutdown")
async def shutdown_API():
    '''
    Game Server calls this endpoint to shut down the player's client after testing is completed.
    Only used if DEBUG is True.
    '''
    os.kill(os.getpid(), signal.SIGTERM)
    logging.info("Player client shutting down...")
    return fastapi.Response(status_code=200, content='Server shutting down...')


# ------------------------
# Main code: register with the server and launch the API.
# ------------------------
if __name__ == "__main__":
    if DEBUG:
        url = "http://127.0.0.1:16200/test"
        logging.basicConfig(level=logging.INFO)
    else:
        url = "http://127.0.0.1:16200/register"
        logging.basicConfig(level=logging.WARNING)

    payload = {
        "name": USER_NAME,
        "address": "127.0.0.1",
        "port": str(PORT)
    }

    try:
        # Register client with the game server.
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

    # Run the client API using uvicorn.
    uvicorn.run(app, host="127.0.0.1", port=PORT)
