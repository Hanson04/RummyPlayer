import requests
from fastapi import FastAPI
import fastapi
from pydantic import BaseModel
import uvicorn
import os
import signal
import logging
#import pytest

"""
By Evan Hanson, Revision 1.2
Written for Hardin-Simmons CSCI-4332 Artificial Intelligence
Revision History
1.0 - API setup
1.1 - Very basic test player
1.2 - Bugs fixed and player improved, should no longer forfeit
"""

# TODO - Change the PORT and USER_NAME Values before running
DEBUG = True
PORT = 10500
USER_NAME = "EvanH"
# TODO - change your method of saving information from the very rudimentary method here
hand = [] # list of cards in our hand
discard = [] # list of cards organized as a stack
cannot_discard = ""

# set up the FastAPI application
app = FastAPI()

# set up the API endpoints
@app.get("/")
async def root():
    ''' Root API simply confirms API is up and running.'''
    return {"status": "Running"}

# data class used to receive data from API POST
class GameInfo(BaseModel):
    game_id: str
    opponent: str
    hand: str

@app.post("/start-2p-game/")
async def start_game(game_info: GameInfo):
    ''' Game Server calls this endpoint to inform player a new game is starting. '''
    # TODO - Your code here - replace the lines below
    global hand
    global discard
    hand = game_info.hand.split(" ")
    hand.sort()
    logging.info("2p game started, hand is "+str(hand))
    return {"status": "OK"}

# data class used to receive data from API POST
class HandInfo(BaseModel):
    hand: str

@app.post("/start-2p-hand/")
async def start_hand(hand_info: HandInfo):
    ''' Game Server calls this endpoint to inform player a new hand is starting, continuing the previous game. '''
    # TODO - Your code here
    global hand
    global discard
    discard = []
    hand = hand_info.hand.split(" ")
    hand.sort()
    logging.info("2p hand started, hand is " + str(hand))
    return {"status": "OK"}

def process_events(event_text):
    ''' Shared function to process event text from various API endpoints '''
    # TODO - Your code here. Everything from here to end of function
    global hand
    global discard
    for event_line in event_text.splitlines():

        if ((USER_NAME + " draws") in event_line or (USER_NAME + " takes") in event_line):
            print("In draw, hand is "+str(hand))
            print("Drew "+event_line.split(" ")[-1])
            hand.append(event_line.split(" ")[-1])
            hand.sort()
            print("Hand is now "+str(hand))
            logging.info("Drew a "+event_line.split(" ")[-1]+", hand is now: "+str(hand))
        if ("discards" in event_line):  # add a card to discard pile
            discard.insert(0, event_line.split(" ")[-1])
        if ("takes" in event_line): # remove a card from discard pile
            discard.pop(0)
        if " Ends:" in event_line:
            print(event_line)

# data class used to receive data from API POST
class UpdateInfo(BaseModel):
    game_id: str
    event: str

@app.post("/update-2p-game/")
async def update_2p_game(update_info: UpdateInfo):
    '''
        Game Server calls this endpoint to update player on game status and other players' moves.
        Typically only called at the end of game.
    '''
    # TODO - Your code here - update this section if you want
    process_events(update_info.event)
    print(update_info.event)
    return {"status": "OK"}

@app.post("/draw/")
async def draw(update_info: UpdateInfo):
    ''' Game Server calls this endpoint to start player's turn with draw from discard pile or draw pile.'''
    global cannot_discard
    # TODO - Your code here - everything from here to end of function
    process_events(update_info.event)
    if len(discard)<1: # If the discard pile is empty, draw from stock
        cannot_discard = ""
        return {"play": "draw stock"}
    if any(discard[0][0] in s for s in hand):
        cannot_discard = discard[0] # if our hand contains a matching card, take it
        return {"play": "draw discard"}
    return {"play": "draw stock"} # Otherwise, draw from stock

def get_of_a_kind_count(hand):
    of_a_kind_count = [0, 0, 0, 0]  # how many 1 of a kind, 2 of a kind, etc in our hand
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
    of_a_kind_count[count] += 1  # Need to get the last card fully processed
    return of_a_kind_count

def get_count(hand, card):
    count = 0
    for check_card in hand:
        if check_card[0] == card[0]: count += 1
    return count

#def test_get_of_a_kind_count():
#    assert get_of_a_kind_count(["2S", "2H", "2D", "7C", "7D", "7S", "7H", "QC", "QD", "QH", "AH"]) == [1, 0, 2, 1]

@app.post("/lay-down/")
async def lay_down(update_info: UpdateInfo):
    ''' Game Server calls this endpoint to conclude player's turn with melding and/or discard.'''
    # TODO - Your code here - everything from here to end of function
    global hand
    global discard
    global cannot_discard
    process_events(update_info.event)
    of_a_kind_count = get_of_a_kind_count(hand)
    if (of_a_kind_count[0]+(of_a_kind_count[1]*2)) > 1:
        print("Need to discard")
        # Too many unmeldable cards, need to discard

        # If we have a 1 of a kind, discard the highest

        if (of_a_kind_count[0]>0):
            print("Discarding a single card")
            logging.info("Discarding a single card")

            # edge case - the last card is 1 of a kind
            if (hand[-1][0] != hand[-2][0]):
                logging.info("Discarding " + hand[-1])
                return {"play": "discard " + hand.pop()}

            for i in range(len(hand)-2,-1, -1):
                if (i==0):
                    logging.info("Discarding "+hand[0])
                    return {"play":"discard "+hand.pop(0)}
                if hand[i][0] != hand[i-1][0] and hand[i][0] != hand[i+1][0]:
                    logging.info("Discarding "+hand[i])
                    return {"play":"discard "+hand.pop(i)}

        elif (of_a_kind_count[1]>=1):
            print("Discarding two of a kind, cannot_discard = "+cannot_discard)
            for i in range(len(hand)-1,-1, -1):
                if (hand[i]!=cannot_discard and get_count(hand,hand[i]) == 2):
                    logging.info("Discarding "+hand[i])
                    return {"play": "discard " + hand.pop(i)}

            logging.info("Discarding " + hand[i])
            return {"play": "discard " + hand.pop(i)}


    # We should be able to meld.

    # First, find the card we discard - if needed
    discard_string = ""
    print(of_a_kind_count)



    if (of_a_kind_count[0] > 0):
        if hand[-1][0] != hand[-2][0]:
            discard_string = " discard " + hand.pop()
        else:
            for i in range(len(hand)-2, -1, -1):
                if (i == 0):
                    discard_string = " discard " + hand.pop(0)
                    break
                if hand[i][0] != hand[i - 1][0] and hand[i][0] != hand[i + 1][0]:
                    discard_string = " discard " + hand.pop(i)
                    break

    # generate our list of meld
    play_string = ""
    last_card = ""
    while (len(hand) > 0):
        card = hand.pop(0)
        if (str(card)[0] != last_card):
            play_string += "meld "
        play_string += str(card) + " "
        last_card = str(card)[0]

    # remove the extra space, and add in our discard if any
    play_string = play_string[:-1]
    play_string += discard_string

    logging.info("Playing: "+play_string)
    return {"play":play_string}

@app.get("/shutdown")
async def shutdown_API():
    ''' Game Server calls this endpoint to shut down the player's client after testing is completed.  Only used if DEBUG is True. '''
    os.kill(os.getpid(), signal.SIGTERM)
    logging.info("Player client shutting down...")
    return fastapi.Response(status_code=200, content='Server shutting down...')


''' Main code here - registers the player with the server via API call, and then launches the API to receive game information '''
if __name__ == "__main__":

    if (DEBUG):
        url = "http://127.0.0.1:16200/test"

        # TODO - Change logging.basicConfig if you want
        logging.basicConfig(filename="RummyPlayer.log", format='%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S',level=logging.INFO)
    else:
        url = "http://127.0.0.1:16200/register"
        # TODO - Change logging.basicConfig if you want
        logging.basicConfig(filename="RummyPlayer.log", format='%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S',level=logging.WARNING)

    payload = {
        "name": USER_NAME,
        "address": "127.0.0.1",
        "port": str(PORT)
    }

    try:
        # Call the URL to register client with the game server
        response = requests.post(url, json=payload)
    except Exception as e:
        print("Failed to connect to server.  Please contact Mr. Dole.")
        exit(1)

    if response.status_code == 200:
        print("Request succeeded.")
        print("Response:", response.json())  # or response.text
    else:
        print("Request failed with status:", response.status_code)
        print("Response:", response.text)
        exit(1)

    # run the client API using uvicorn
    uvicorn.run(app, host="127.0.0.1", port=PORT)