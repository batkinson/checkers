#!/usr/bin/env python
import sys
from SocketServer import ThreadingTCPServer, StreamRequestHandler
from internals import RED, BLACK, Board, Piece, CheckersException, opponent
from threading import RLock
from time import time
from functools import wraps
import logging as log


PRUNE_IDLE_SECS = 60 * 10  # 10 Minutes


LIST, JOIN, NEW, LEAVE, QUIT, MOVE, SHUTDOWN, TURN, BOARD = 'LIST', 'JOIN', 'NEW', 'LEAVE', 'QUIT', 'MOVE', 'SHUTDOWN',\
                                                            'TURN', 'BOARD'
ERROR, OK, STATUS = 'ERROR', 'OK', 'STATUS'
JOINED, YOU_ARE, LEFT, MOVED, CAPTURED, KING, WAIT, WINNER = 'JOINED', 'YOU_ARE', 'LEFT', 'MOVED', 'CAPTURED', 'KING', \
                                                             'waiting', 'WINNER'

COMMANDS = set([LIST, JOIN, NEW, LEAVE, QUIT, MOVE, BOARD, TURN, SHUTDOWN])
STATUSES = set([JOINED, LEFT, MOVED, CAPTURED, WINNER, YOU_ARE, BOARD, TURN, LIST])


class ServerException(Exception):

    def __init__(*args, **kwargs):
        Exception.__init__(*args, **kwargs)


class RequestHandler(StreamRequestHandler):

    def __init__(self, *args, **kwargs):
        StreamRequestHandler.__init__(self, *args, **kwargs)
        self.player = None
        self.game = None

    def send_line(self, line):
        self.wfile.write(line + '\r\n')
        log.debug('%s <= %s', ':'.join(map(str, self.client_address)), line)

    def flush(self):
        self.wfile.flush()

    def handle(self):

        client = ':'.join(map(str, self.client_address))

        log.debug('%s connected', client)

        game = player = None

        while True:

            req = self.rfile.readline().strip()

            log.debug('%s => %s', client, req)

            req = req.split()

            if not req:
                continue

            cmd = req.pop(0)

            try:
                if cmd in COMMANDS:
                    result = [OK]
                    if cmd == QUIT:
                        if game:
                            game.leave(player)
                        break
                    elif not game and cmd == NEW:
                        game, player = self.server.new_game(self)
                    elif cmd == JOIN:
                        orig_game = None
                        if game:
                            orig_game, orig_player = game, player
                        game_id = int(req.pop(0))
                        game, player = self.server.join_game(game_id, self)
                        if orig_game:
                            orig_game.leave(orig_player)
                    elif cmd == LIST:
                        games = self.server.get_games()
                        self.send_line('STATUS LIST ' + ' '.join(
                            [str(g.id) for g in games if not game or game is not g]))
                    elif game and cmd == LEAVE:
                        game.leave(player)
                        game = player = None
                    elif game and cmd == BOARD:
                        self.send_line('STATUS BOARD %s' % repr(game))
                    elif game and cmd == MOVE:
                        src, dst = (int(req.pop(0)), int(req.pop(0))), (int(req.pop(0)), int(req.pop(0)))
                        game.make_move(src, dst, player)
                    elif game and cmd == TURN:
                        self.send_line('STATUS TURN %s' % game.turn)
                    elif cmd == SHUTDOWN:
                        self.server.shutdown()
                    else:
                        raise ServerException('invalid command')
                else:
                    result = [ERROR, 'invalid command']
            except ServerException as error:
                result = [ERROR, error.message]

            self.send_line(' '.join(result))
            self.flush()

        log.debug('%s finishing', client)


def game_interaction(fn):
    @wraps(fn)
    def update_interaction_time(self, *args, **kwargs):
        result = fn(self, *args, **kwargs)
        self.last_interaction = time()
        return result
    return update_interaction_time


class Game:

    def __init__(self):
        self.id = id(self)
        self.board = Board()
        self.lock = RLock()
        self.players = {RED: None, BLACK: None}
        self.last_interaction = time()
        for player, x, y in self.board.start_positions():
            self.board.add_piece(Piece(player), (x, y))

    def send_status(self, message, player=None):
        for p in self.players:
            if (player is None or p == player) and self.players[p]:
                self.players[p].send_line(message)

    @game_interaction
    def join(self, player_handler):
        with self.lock:
            if not self.open_seats:
                raise ServerException('no available seats')
            open_player = self.open_seats[0]
            self.players[open_player] = player_handler
            self.send_status(' '.join([STATUS, BOARD, repr(self)]), player=open_player)
            self.send_status(' '.join([STATUS, JOINED, open_player]), player=opponent[open_player])
            self.send_status(' '.join([STATUS, YOU_ARE, open_player]), player=open_player)
            self.send_status(' '.join([STATUS, TURN, self.turn]))
            return open_player

    @game_interaction
    def leave(self, player):
        with self.lock:
            if player in self.players and self.players[player]:
                self.players[player] = None
                self.send_status(' '.join([STATUS, LEFT, player]))
                self.send_status(' '.join([STATUS, TURN, self.turn]))

    @property
    def open_seats(self):
        with self.lock:
            seats = []
            for player in [RED, BLACK]:
                if not self.players[player]:
                    seats.append(player)
            return seats

    @property
    def turn(self):
        with self.lock:
            if self.open_seats:
                return WAIT
            return self.board.turn

    @property
    def winner(self):
        with self.lock:
            return self.board.winner()

    @game_interaction
    def make_move(self, src, dst, player):
        with self.lock:
            if self.open_seats:
                raise ServerException('waiting for player')
            if not src in self.board:
                raise ServerException('invalid move source')
            if self.board[src].player != player:
                raise ServerException('not your piece')
            try:
                was_king = self.board[src].king
                move_status = [STATUS, MOVED] + [str(i) for i in src] + [str(i) for i in dst]
                captured = self.board.move(src, dst)
                self.send_status(' '.join(move_status))
                if captured:
                    self.send_status(' '.join([STATUS, CAPTURED] + [str(i) for i in captured.location]))
                if not was_king and self.board[dst].king:
                    self.send_status(' '.join([STATUS, KING] + [str(i) for i in dst]))
                self.send_status(' '.join([STATUS, TURN, self.turn]))
                if self.winner:
                    self.send_status(' '.join([STATUS, WINNER, self.winner]))
            except CheckersException as ce:
                raise ServerException(ce.message)

    def __repr__(self):
        with self.lock:
            return repr(self.board)


class Server(ThreadingTCPServer):

    def __init__(self, log_level=log.INFO, ip='0.0.0.0', port=5000):
        log.basicConfig(level=log_level)
        self.games = {}
        self.lock = RLock()
        self.allow_reuse_address = True
        log.info('starting server on port %s:%s', ip, str(port))
        ThreadingTCPServer.__init__(self, (ip, port), RequestHandler)

    def _prune_idle_games(self):
        with self.lock:
            now = time()
            to_prune = []
            for key, game in self.games.items():
                if game.last_interaction < now - PRUNE_IDLE_SECS:
                    game = self.games.pop(key)

    def get_games(self):
        with self.lock:
            try:
                return [g for g in self.games.values() if g.open_seats and not g.winner]
            finally:
                self._prune_idle_games()

    def new_game(self, handler):
        with self.lock:
            new_game = Game()
            self.games[new_game.id] = new_game
            return self.join_game(new_game.id, handler)

    def join_game(self, game_id, handler):
        with self.lock:
            if game_id in self.games:
                game = self.games[game_id]
                player = game.join(handler)
                return game, player
            raise ServerException('game not available')


if __name__ == '__main__':
    server = None
    log_level = log.INFO
    try:
        if len(sys.argv) > 1:
            port = int(sys.argv[1])
            server = Server(log_level=log_level, port=port)
        else:
            server = Server(log_level=log_level)
        server.serve_forever()
    except Exception as e:
        log.exception(e)
