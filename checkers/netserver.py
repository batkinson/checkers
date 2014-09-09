#!/usr/bin/env python
import sys
from SocketServer import ThreadingTCPServer, StreamRequestHandler
from internals import RED, BLACK, Board, Piece, CheckersException
from threading import RLock
from time import time
from functools import wraps
import logging as log


PRUNE_IDLE_SECS = 60 * 10  # 10 Minutes


LIST, JOIN, NEW, LEAVE, QUIT, MOVE, SHUTDOWN, TURN, BOARD, SPECTATE = 'LIST', 'JOIN', 'NEW', 'LEAVE', 'QUIT', 'MOVE',\
                                                                      'SHUTDOWN', 'TURN', 'BOARD', 'SPECTATE'
ERROR, OK, STATUS = 'ERROR', 'OK', 'STATUS'
JOINED, YOU_ARE, LEFT, MOVED, CAPTURED, KING, WAIT, WINNER, GAME_ID = 'JOINED', 'YOU_ARE', 'LEFT', 'MOVED', 'CAPTURED',\
                                                                      'KING', 'waiting', 'WINNER', 'GAME_ID'

COMMANDS = set([LIST, JOIN, NEW, LEAVE, QUIT, MOVE, BOARD, TURN, SHUTDOWN, SPECTATE])
STATUSES = set([JOINED, LEFT, MOVED, CAPTURED, WINNER, YOU_ARE, BOARD, TURN, LIST, GAME_ID])


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

            req = self.rfile.readline()

            if not req:
                break;

            req = req.strip()
            
            log.debug('%s => %s', client, req)

            req = req.split()
            cmd = req.pop(0)

            try:
                if cmd in COMMANDS:
                    result = [OK]
                    if cmd == QUIT:
                        if game:
                            game.leave(self)
                        break
                    elif not game and cmd == NEW:
                        game, player = self.server.new_game(self)
                    elif cmd == JOIN:
                        orig_game = None
                        if game:
                            orig_game = game
                        game_id = int(req.pop(0))
                        game, player = self.server.join_game(game_id, self)
                        if orig_game:
                            orig_game.leave(self)
                    elif cmd == SPECTATE:
                        orig_game = None
                        if game:
                            orig_game = game
                        game_id = int(req.pop(0))
                        game = self.server.spectate_game(game_id, self)
                        if orig_game:
                            orig_game.leave(self)
                    elif cmd == LIST:
                        list_type = None
                        status_prefix = 'STATUS LIST '
                        if req:
                            list_type = req.pop(0)
                        if list_type and list_type == SPECTATE:
                            games = self.server.get_unfinished_games()
                            status_prefix += SPECTATE + ' '
                        else:
                            games = self.server.get_open_games()
                        self.send_line(status_prefix + ' '.join(
                            [str(g.id) for g in games if not game or game is not g]))
                    elif game and cmd == LEAVE:
                        game.leave(self)
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
        self.spectators = []
        for player, x, y in self.board.start_positions():
            self.board.add_piece(Piece(player), (x, y))

    def send_status(self, message, include=None, exclude=None):
        notify_set = [handler for handler in (self.players.values() + self.spectators)
                      if handler
                      and (include is None or handler in include)
                      and (exclude is None or handler not in exclude)]
        for handler in notify_set:
            handler.send_line(message)

    @game_interaction
    def join(self, player_handler):
        with self.lock:
            if not self.open_seats:
                raise ServerException('no available seats')
            open_player = self.open_seats[0]
            self.players[open_player] = player_handler
            joining_player = [player_handler]
            self.send_status(' '.join([STATUS, GAME_ID, str(self.id)]), include=joining_player)
            self.send_status(' '.join([STATUS, BOARD, repr(self)]), include=joining_player)
            self.send_status(' '.join([STATUS, JOINED, open_player]), exclude=joining_player)
            self.send_status(' '.join([STATUS, YOU_ARE, open_player]), include=joining_player)
            self.send_status(' '.join([STATUS, TURN, self.turn]))
            return open_player

    def spectate(self, handler):
        with self.lock:
            joining_spectator = [handler]
            if handler not in self.spectators:
                self.spectators.append(handler)
                self.send_status(' '.join([STATUS, GAME_ID, str(self.id)]), include=joining_spectator)
                self.send_status(' '.join([STATUS, BOARD, repr(self)]), include=joining_spectator)
                self.send_status(' '.join([STATUS, TURN, self.turn]), include=joining_spectator)

    @game_interaction
    def leave(self, client):
        with self.lock:
            for player, handler in self.players.items():
                if handler is client:
                    self.players[player] = None
                    self.send_status(' '.join([STATUS, LEFT, player]))
                    self.send_status(' '.join([STATUS, TURN, self.turn]))
            if client in self.spectators:
                self.spectators.remove(client)

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
            for key, game in self.games.items():
                if game.last_interaction < now - PRUNE_IDLE_SECS:
                    self.games.pop(key)

    def get_games(self):
        with self.lock:
            self._prune_idle_games()
            return [g for g in self.games.values()]

    def get_open_games(self):
        return [g for g in self.get_games() if g.open_seats and not g.winner]

    def get_unfinished_games(self):
        return [g for g in self.get_games() if not g.winner]

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

    def spectate_game(self, game_id, handler):
        with self.lock:
            if game_id in self.games:
                game = self.games[game_id]
                game.spectate(handler)
                return game
            raise ServerException('game not available')


if __name__ == '__main__':

    from argparse import ArgumentParser

    arg_p = ArgumentParser(description='A network-based checkers server')

    arg_p.add_argument('--interface', help='interface to bind to', default='0.0.0.0')
    arg_p.add_argument('--port', help='port to bind to', type=int, default='5000')
    arg_p.add_argument('--log-level', help='diagnostic logging level', choices=['DEBUG', 'INFO'], default='INFO')

    args = arg_p.parse_args(args=sys.argv[1:])

    try:
        server = Server(ip=args.interface, port=args.port, log_level=log.getLevelName(args.log_level))
        server.serve_forever()
    except Exception as e:
        log.exception(e)
