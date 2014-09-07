from internals import Board, InvalidMoveException
from socket import socket, AF_INET, SOCK_STREAM, TCP_NODELAY, IPPROTO_TCP, timeout, error
from select import select
from netserver import WAIT
import logging as log
from StringIO import StringIO


class StatusHandler:

    def handle_winner(self, player):
        pass

    def handle_joined(self, player):
        pass

    def handle_left(self, player):
        pass

    def handle_moved(self, src, dst):
        pass

    def handle_captured(self, loc):
        pass

    def handle_you_are(self, player):
        pass

    def handle_board(self, board):
        pass

    def handle_turn(self, player):
        pass

    def handle_list(self, game_list):
        pass


class Client:

    def __init__(self, ip='127.0.0.1', port=5000, status_handler=None):
        self.player = None
        self.ip = ip
        self.port = port
        self.status_handler = status_handler
        self.socket = socket(AF_INET, SOCK_STREAM)
        self.socket.setsockopt(IPPROTO_TCP, TCP_NODELAY, True)
        self.socket.connect((ip, port))
        self.socket.setblocking(False)
        self.buf = StringIO()
        self.cmd_listeners = []
        self.status_lines = []

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

    def read(self):

        def is_status_line(line):
            return line.startswith('STATUS')

        (readers, _, _) = select([self.socket], [], [], 0)
        result = []
        if readers:
            lines = self._read_lines()
            for line in lines:
                log.debug('<= %s', line)
                result.append(line)
        self.status_lines += filter(is_status_line, result)
        return self.process_status()

    def process_status(self):
        did_something = False
        if not self.status_handler:
            return
        while self.status_lines:
            line = self.status_lines.pop(0)
            try:
                line = line.strip().split(' ')[1:]
                status = line[0]
                line = line[1:]
                if status == 'WINNER':
                    self.status_handler.handle_winner(line[0])
                elif status == 'JOINED':
                    self.status_handler.handle_joined(line[0])
                elif status == 'LEFT':
                    self.status_handler.handle_left(line[0])
                elif status == 'MOVED':
                    src, dst = (int(line[0]), int(line[1])), (int(line[2]), int(line[3]))
                    self.status_handler.handle_moved(src, dst)
                elif status == 'CAPTURED':
                    loc = (int(line[0]), int(line[1]))
                    self.status_handler.handle_captured(loc)
                elif status == 'YOU_ARE':
                    self.status_handler.handle_you_are(line[0])
                elif status == 'BOARD':
                    board = Board()
                    board.load_str(line[0])
                    self.status_handler.handle_board(board)
                elif status == 'TURN':
                    self.status_handler.handle_turn(line[0])
                elif status == 'LIST':
                    self.status_handler.handle_list(line)
                did_something = True
            except Exception as e:
                log.exception(e)
        return did_something

    def send_line(self, line):
        self.socket.sendall(line + '\r\n')
        log.debug("=> %s", line)

    def list(self):
        self.send_line('LIST')

    def join(self, game_id):
        self.send_line('JOIN %s' % game_id)

    def leave(self):
        self.send_line('LEAVE')

    def quit(self):
        self.send_line('QUIT')

    def shutdown(self):
        self.send_line('SHUTDOWN')

    def new_game(self):
        self.send_line('NEW')

    def move(self, src, dst):
        self.send_line('MOVE %s %s', ' '.join(src[0], src[1], dst[0], dst[1]))

    def board(self):
        self.send_line('BOARD')

    def turn(self):
        self.send_line('TURN')


class NetBoard(Board):

    def __init__(self, ip='127.0.0.1', port=5000, handler=StatusHandler()):
        Board.__init__(self)
        self.turn = WAIT
        self.player = None
        self.client = Client(ip=ip, port=port, status_handler=handler)
        log.info('trying game server at %s:%s', ip, port)
        self.connect()

    def update(self):
        self.client.read()

    def connect(self):
        self.client.list()

    def move(self, src, dst):
        if self._valid_move(src, dst):
            self.client.send_line('MOVE %s %s %s %s' % (src[0], src[1], dst[0], dst[1]))
        else:
            raise InvalidMoveException("invalid move from %s to %s" % (src, dst))

