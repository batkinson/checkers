#!/usr/bin/env python

import socket
import select
from StringIO import StringIO
from functools import wraps
from threaded_server import ServerPublisher, COMMANDS, SPECTATE, OK, ERROR
from threaded_server import Game, ServerException, PRUNE_IDLE_SECS
import logging as log
from socket import timeout, error
from time import time


def cleanup_on_failure(fn):
    @wraps(fn)
    def remove_handler(self, *args, **kwargs):
        try:
            return fn(self, *args, **kwargs)
        except Exception as e:
            self.cleanup()
            raise e
    return remove_handler


class UserHandler(object):

    rbufsize = -1
    wbufsize = 0

    def __init__(self, server, sock):
        self.server = server
        self.socket = sock
        self.commands = dict((cmd, getattr(self, "_%s" % cmd.lower())) for cmd in COMMANDS)
        self.buf = StringIO()
        self.client = ":".join(map(str, sock.getpeername()))
        self.player = None
        self.game = None
        self.rfile = self.socket.makefile('rb', self.rbufsize)
        self.wfile = self.socket.makefile('wb', self.wbufsize)

    @cleanup_on_failure
    def send_line(self, line):
        self.wfile.write(line + '\r\n')
        log.debug('%s <= %s', self.client, line)

    @cleanup_on_failure
    def flush(self):
        if not self.wfile.closed:
            self.wfile.flush()

    def cleanup(self):
        if self.game:
            log.debug('%s leaving game', self.client)
            self.game.leave(self)
            self.game = None
        self.server.remove_handler(self.socket)

    def close(self):
        log.debug("%s closing", self.client)
        for fd in [self.wfile, self.rfile]:
            try:
                fd.close()
            except Exception as e:
                log.exception('failed to close file descriptor', e.message)

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
        self.cleanup()

    def _shutdown(self, *args):
        """Handler for the SHUTDOWN command, tells server to shutdown after all clients disconnect."""
        self.server.shutdown()

    def _read_lines(self):
        out_of_data = False
        while not out_of_data:
            try:
                data = self.socket.recv(4096)
            except (timeout, error) as e:
                out_of_data = True
            else:
                if len(data) == 0:
                    out_of_data = True
                else:
                    self.buf.seek(0, 2)  # Append to end of buffer
                    self.buf.write(data)
        self.buf.seek(0)
        result = self.buf.readlines()
        if result:
            self.buf.buf = self.buf.getvalue()[self.buf.pos:]
            self.buf.len = len(self.buf.buf)
            self.buf.pos = 0
        return map(str.strip, result)

    def handle(self):
        """Handles input arriving by parsing and executing complete commands."""
        req_lines = self._read_lines()
        if not req_lines:
            self.cleanup()
        for req in req_lines:
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


class Server(object):

    """A non-blocking network server."""

    address_family = socket.AF_INET

    socket_type = socket.SOCK_STREAM

    request_queue_size = 5

    allow_reuse_address = False

    def __init__(self, log_level=log.INFO, ip='0.0.0.0', port=5000, prune_inactive=PRUNE_IDLE_SECS):
        log.basicConfig(level=log_level)
        self.games = {}
        self.allow_reuse_address = True
        self.prune_inactive = prune_inactive
        self.server_address = (ip, port)
        self.running = True
        self.socket = socket.socket(self.address_family, self.socket_type)
        self.readable = [self.socket]
        self.writable = []
        self.errored = []
        self.sockets_to_close = []
        self.handlers = {}

    def bind(self):
        """Binds the server's socket."""
        if self.allow_reuse_address:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        self.socket.bind(self.server_address)
        self.server_address = self.socket.getsockname()

    def activate(self):
        """Starts listening on the server's socket."""
        self.socket.listen(self.request_queue_size)

    def new_handler(self, sock):
        self.handlers[sock] = UserHandler(self, sock)

    def remove_handler(self, sock):
        if sock in self.handlers:
            self.sockets_to_close.append(sock)

    def cleanup(self, sockets=[]):
        for s in self.sockets_to_close + sockets:
            self.readable.remove(s)
            self.errored.remove(s)
            handler = self.handlers.pop(s)
            handler.close()
            s.close()
        self.sockets_to_close = []

    def start(self):
        """Starts servicing connections."""
        log.info('started server on %s:%s', self.server_address[0], self.server_address[1])
        while self.running:
            readable, writable, errored = select.select(self.readable, self.writable, self.errored)
            self.cleanup(errored)
            for s in readable:
                if s is self.socket:
                    client_socket, client_address = self.socket.accept()
                    client_socket.setblocking(False)
                    log.debug('%s connected', ":".join(map(str, client_address)))
                    self.new_handler(client_socket)
                    self.readable.append(client_socket)
                    self.errored.append(client_socket)
                else:
                    if s in self.handlers:
                        self.handlers[s].handle()
            self.cleanup()

    def _prune_idle_games(self):
        now = time()
        for key, game in self.games.items():
            if game.last_interaction < now - self.prune_inactive:
                self.games.pop(key)
                log.debug('abandoning game %s after %s seconds of inactivity', game.id, self.prune_inactive)

    def get_games(self):
        self._prune_idle_games()
        return [g for g in self.games.values()]

    def get_open_games(self):
        return [g for g in self.get_games() if g.open_seats and not g.winner]

    def get_unfinished_games(self):
        return [g for g in self.get_games() if not g.winner]

    def new_game(self, handler):
        new_game = Game()
        self.games[new_game.id] = new_game
        return self.join_game(new_game.id, handler)

    def join_game(self, game_id, handler):
        if game_id in self.games:
            game = self.games[game_id]
            player = game.join(handler)
            return game, player
        raise ServerException('game not available')

    def spectate_game(self, game_id, handler):
        if game_id in self.games:
            game = self.games[game_id]
            game.spectate(handler)
            return game
        raise ServerException('game not available')

    def serve_forever(self):
        self.bind()
        self.activate()
        self.start()


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



