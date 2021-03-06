#!/usr/bin/env python
import sys
from SocketServer import ThreadingTCPServer, StreamRequestHandler
from internals import RED, BLACK, Board, Piece, CheckersException
from threading import RLock
from time import time
from functools import wraps
from idgen import gen_id
from socket import inet_aton, gethostname
from zeroconf import Zeroconf, ServiceInfo
import logging as log


PRUNE_IDLE_SECS = 5 * 60  # 5 Minutes


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


def cleanup_on_failure(fn):
    @wraps(fn)
    def remove_handler(self, *args, **kwargs):
        try:
            return fn(self, *args, **kwargs)
        except Exception as e:
            self.cleanup()
            raise e
    return remove_handler


class RequestHandler(StreamRequestHandler):

    def __init__(self, *args, **kwargs):
        self.commands = dict((cmd, getattr(self, "_%s" % cmd.lower())) for cmd in COMMANDS)
        self.client = None
        self.player = None
        self.game = None
        self.servicing = True
        StreamRequestHandler.__init__(self, *args, **kwargs)

    @cleanup_on_failure
    def send_line(self, line):
        self.wfile.write(line + '\r\n')
        log.debug('%s <= %s', self.client, line)

    @cleanup_on_failure
    def flush(self):
        self.wfile.flush()

    def cleanup(self):
        if self.game:
            log.debug('%s leaving game', self.client)
            self.game.leave(self)
            self.game = None

    def get_command(self, cmd_str):
        """Returns the handler method corresponding to the given command."""
        try:
            return self.commands[cmd_str]
        except KeyError:
            raise ServerException('invalid command')

    def _new(self, *args):
        """Handler for NEW command, creates and joins player to game."""
        if self.game:
            raise ServerException('already playing a game')
        self.game, self.player = self.server.new_game(self)

    def _join(self, req):
        """Handler for JOIN command, joins player to existing game."""
        orig_game = None
        if self.game:
            orig_game = self.game
        game_id = req.pop(0)
        self.game, self.player = self.server.join_game(game_id, self)
        if orig_game:
            orig_game.leave(self)

    def _spectate(self, req):
        """Handler for SPECTATE command, joins spectator to existing game."""
        orig_game = None
        if self.game:
            orig_game = self.game
        game_id = req.pop(0)
        self.game = self.server.spectate_game(game_id, self)
        if orig_game:
            orig_game.leave(self)

    def _list(self, req):
        """Handler for LIST command, lists game for play or spectating. Excludes current game."""
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
            [str(g.id) for g in games if not self.game or self.game is not g]))

    def _leave(self, *args):
        """Handler for LEAVE command, removes player or spectator from game."""
        if not self.game:
            raise ServerException('not playing a game')
        self.game.leave(self)
        self.game = self.player = None

    def _board(self, *args):
        """Handler for BOARD command, sends player or spectator the board status."""
        if not self.game:
            raise ServerException('not playing a game')
        self.send_line('STATUS BOARD %s' % repr(self.game))

    def _move(self, req):
        """Handler for MOVE command, moves the player's from the specified source to specified destination."""
        if not self.game:
            raise ServerException('not playing a game')
        src, dst = (int(req.pop(0)), int(req.pop(0))), (int(req.pop(0)), int(req.pop(0)))
        self.game.make_move(src, dst, self.player)

    def _turn(self, *args):
        """Handler for the TURN command, sends the player or spectator the turn status."""
        self.send_line('STATUS TURN %s' % self.game.turn)

    def _quit(self, *args):
        """Handler for the QUIT command, terminates the connection with client."""
        self.servicing = False

    def _shutdown(self, *args):
        """Handler for the SHUTDOWN command, tells server to shutdown after all clients disconnect."""
        self.server.shutdown()

    def handle(self):

        self.client = ':'.join(map(str, self.client_address))

        log.debug('%s connected', self.client)

        self.game = self.player = None

        while self.servicing:

            req = self.rfile.readline()

            if not req:
                break

            req = req.strip()
            
            log.debug('%s => %s', self.client, req)

            req = req.split()
            cmd = req.pop(0)

            try:
                self.get_command(cmd)(req)
                result = [OK]
            except Exception as error:
                result = [ERROR, error.message]

            self.send_line(' '.join(result))
            self.flush()

        log.debug('%s finishing', self.client)
        self.cleanup()


def game_interaction(fn):
    @wraps(fn)
    def update_interaction_time(self, *args, **kwargs):
        result = fn(self, *args, **kwargs)
        self.last_interaction = time()
        return result
    return update_interaction_time


class Game:

    def __init__(self):
        self.id = gen_id()
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
            leaving_client = [client]
            for player, handler in self.players.items():
                if handler is client:
                    self.players[player] = None
                    self.send_status(' '.join([STATUS, LEFT, player]), exclude=leaving_client)
                    self.send_status(' '.join([STATUS, TURN, self.turn]), exclude=leaving_client)
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

    def __init__(self, log_level=log.INFO, ip='0.0.0.0', port=5000, prune_inactive=PRUNE_IDLE_SECS):
        log.basicConfig(level=log_level)
        self.games = {}
        self.lock = RLock()
        self.allow_reuse_address = True
        self.prune_inactive = prune_inactive
        ThreadingTCPServer.__init__(self, (ip, port), RequestHandler)
        self.host, self.port = self.server_address
        log.info('started server on %s:%s', self.host, self.port)

    def _prune_idle_games(self):
        with self.lock:
            now = time()
            for key, game in self.games.items():
                if game.last_interaction < now - self.prune_inactive:
                    self.games.pop(key)
                    log.debug('abandoning game %s after %s seconds of inactivity', game.id, self.prune_inactive)

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


class ServerPublisher:

    def __init__(self):
        self.zero_conf = Zeroconf()

    def publish(self, host, port):
        log.debug('publishing server at %s:%s' % (host, port))
        hostname = gethostname()
        service_info = ServiceInfo("_checkers._tcp.local.", "%s._checkers._tcp.local." % hostname,
                                   inet_aton(host), port, 0, 0, {}, server=hostname + '.local')
        self.zero_conf.registerService(service_info)

    def shutdown(self):
        log.debug('shutting down server publisher')
        self.zero_conf.unregisterAllServices()
        self.zero_conf.close()


if __name__ == '__main__':

    import atexit
    from argparse import ArgumentParser

    def parse_arguments():
        arg_p = ArgumentParser(description='A network-based checkers server')
        arg_p.add_argument('--interface', help='interface to bind to', default='0.0.0.0')
        arg_p.add_argument('--port', help='port to bind to', type=int, default='0')
        arg_p.add_argument('--log-level', help='diagnostic logging level', choices=['DEBUG', 'INFO'], default='INFO')
        arg_p.add_argument('--prune-inactive', help='prune games after n seconds inactive', type=int,
                           default=PRUNE_IDLE_SECS)
        arg_p.add_argument('--zeroconf', help='register as a zeroconf service', action='store_true', default=False)
        return arg_p.parse_args()

    def publish_server(server):
        server_publisher = ServerPublisher()
        server_publisher.publish(server.host, server.port)
        atexit.register(server_publisher.shutdown)

    args = parse_arguments()

    try:
        server = Server(ip=args.interface, port=args.port, log_level=log.getLevelName(args.log_level),
                        prune_inactive=args.prune_inactive)
        if args.zeroconf:
            publish_server(server)
        server.serve_forever()
    except Exception as e:
        log.exception(e)
