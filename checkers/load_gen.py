#!/usr/bin/env python

from netclient import Client, StatusHandler
from internals import RED, BLACK


class PlayerBot(object, StatusHandler):

    input_files = {RED: 'game-data/moves-red', BLACK: 'game-data/moves-black'}

    def __init__(self):
        self.game_id = None
        self.finished = False
        self.player = None
        self.moves = []
        self.client = Client(status_handler=self)

    def new_game(self):
        self.client.new_game()

    def join(self, game_id):
        self.client.join(game_id)

    @staticmethod
    def load_moves(filename):
        with open(filename, 'r') as move_file:
            return move_file.readlines()

    def handle_game_id(self, game_id):
        self.game_id = game_id

    def handle_you_are(self, player):
        self.player = player
        self.moves = map(str.strip, self.load_moves(self.input_files[player]))

    def handle_turn(self, player):
        if player == self.player and self.moves:
            move = self.moves.pop(0)
            self.client.send_line(move)

    def handle_winner(self, player):
        self.finished = True
        self.client.quit()

    def process_events(self):
        self.client.read()


if __name__ == '__main__':
    GAME_COUNT = 500
    games = []
    for game_num in xrange(1, GAME_COUNT+1):
        print "p1: creating game %s" % game_num
        p1 = PlayerBot()
        p1.new_game()
        games.append([p1, None])
    for game in games:
        game[0].process_events()  # Ensures player 1 has game id
        game_id = game[0].game_id
        print "p2: joining game %s" % game_id
        p2 = PlayerBot()
        p2.join(game_id)
        game[1] = p2
    while games:
        for game in games:
            for player in game:
                print "updating %s:%s" % (player.game_id, player.player)
                player.process_events()
        games = [g for g in games if not (g[0].finished and g[1].finished)]
