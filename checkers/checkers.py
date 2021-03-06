#!/usr/bin/env python
#
# Checkers - a simple checkers, adapted from Clare's checkers
#
# Released under the GNU General Public License

import os
import sys
import logging as log
import pygame
from pygame import Rect
from pygame import mixer
from pygame.sprite import Sprite, RenderUpdates, GroupSingle
from pygame.constants import QUIT, MOUSEBUTTONDOWN, MOUSEBUTTONUP
from pygame.time import Clock
from internals import Board, Piece, RED, BLACK, InvalidMoveException, players
from netclient import NetBoard, StatusHandler, SPECTATE
from socket import inet_ntoa
from zeroconf import Zeroconf, ServiceBrowser

AUTO_DISCOVERY_TYPE = '_checkers._tcp'
AUTO_DISCOVERY_WAIT = 30
WHITE = (255, 255, 255)
TILE_WIDTH = 75
BORDER_WIDTH = 50
SCREEN_RES = (650, 650)
ORIGIN = (0, 0)


def game_to_screen(game_x_or_y, center=True):
    """Translates the abstract game grid coordinates to screen coordinates."""
    grid_coord = TILE_WIDTH * game_x_or_y + (BORDER_WIDTH / 2)
    if center:
        grid_coord += (TILE_WIDTH / 2)
    return grid_coord


class Images:

    image_cache = {}

    @classmethod
    def load(cls, name):
        """ Load image and return image object"""
        fullname = os.path.join('..', 'images', name)
        if fullname in cls.image_cache:
            return cls.image_cache[fullname], cls.image_cache[fullname].get_rect()
        try:
            log.debug('loading: %s', fullname)
            image = pygame.image.load(fullname)
            if image.get_alpha() is None:
                image = image.convert()
            else:
                image = image.convert_alpha()
            cls.image_cache[fullname] = image
            return image, image.get_rect()
        except pygame.error, message:
            log.exception('failed to load image %s: %s', fullname, message)
            raise SystemExit


class Sounds:

    sound_cache = {}

    @classmethod
    def play(cls, name):
        """Loads a sound and plays it immediately."""
        fullname = os.path.join('..', 'sounds', name)
        if fullname in cls.sound_cache:
            cls.sound_cache[fullname].play()
        else:
            log.debug('loading: %s', fullname)
            sound = pygame.mixer.Sound(fullname)
            cls.sound_cache[fullname] = sound
            sound.play()


class PieceSprite(Piece, Sprite):

    """A sprite for a single piece."""

    def __init__(self, player):
        Sprite.__init__(self)
        Piece.__init__(self, player)
        self.image = pygame.Surface((TILE_WIDTH, TILE_WIDTH), pygame.SRCALPHA, 32).convert_alpha()
        self.rect = self.image.get_rect()

    def update_from_board(self):
        self.rect.centerx, self.rect.centery = [game_to_screen(v) for v in self.location]

    def update(self, turn):
        self.image = pygame.Surface((TILE_WIDTH, TILE_WIDTH), pygame.SRCALPHA, 32).convert_alpha()
        if self.player == turn:
            image, image_rect = Images.load('piece-corona.png')
            self.image.blit(image, image_rect)
        image_name = '%s-piece' % self.player
        if self.king:
            image_name += '-king'
        image_name += '.png'
        image, image_rect = Images.load(image_name)
        self.image.blit(image, image_rect)


class Square(Rect):

    """An abstraction for game board spaces."""

    def __init__(self, row, col):
        self.row, self.col = row, col
        self.x, self.y = [game_to_screen(v, False) for v in (col, row)]
        self.width, self.height = TILE_WIDTH, TILE_WIDTH


class Text(Sprite):

    """Allows rendering text as sprites."""

    def __init__(self, text, font, color):
        Sprite.__init__(self)
        self.text, self.font, self.color = text, font, color
        self._update()

    def _update(self):
        self.image = self.font.render(self.text, True, self.color)
        self.rect = self.image.get_rect()

    def update(self, *args):
        self._update()


class Game(StatusHandler):

    def __init__(self, title='Checkers', log_drag=False, show_fps=False, ip='127.0.0.1', port=5000, spectate=False):
        self.game_running = True
        self.player = None
        self.log_drag = log_drag
        self.show_fps = show_fps
        self.window_title = title
        self.game = NetBoard(handler=self, ip=ip, port=port, spectate=spectate)
        # Initialize Game Groups
        self.board_spaces = set()
        self.pieces = RenderUpdates()
        self.piece_selected = GroupSingle()
        self.bg_text = RenderUpdates()
        self.fg_text = RenderUpdates()
        self.current_piece_position = ORIGIN
        self.screen = None
        self.fps_clock = None
        self.font = None
        self.background = None
        self.background_rect = None
        self.fps_text = None
        self.winner_text = None
        self.turn_text = None
        self.player_text = None
        self.game_id_text = None

    def handle_game_id(self, game_id):
        self.game_id_text.text = "Game: %s" % game_id

    def handle_list(self, game_list, list_type):

        if list_type == SPECTATE and game_list:
            game_id = game_list[0]
            self.game.client.spectate(game_id)
            self.player_text.text = 'You are a spectator'
        elif not list_type and game_list:
            game_id = game_list[0]
            self.game.client.join(game_id)
        elif not list_type and not game_list:
            self.game.client.new_game()

    def handle_board(self, board):
        for piece in board:
            new_piece = PieceSprite(piece.player)
            new_piece.king = piece.king
            self.game.add_piece(new_piece, piece.location)
            new_piece.update_from_board()
            self.pieces.add(new_piece)

    def handle_turn(self, player):
        self.game.turn = player

    def handle_you_are(self, player):
        self.player = player

    def handle_moved(self, src, dst):
        moved_pieces = [p for p in self.pieces if p.location == src]
        Board.move(self.game, src, dst)
        if moved_pieces:
            moved_pieces[0].update_from_board()
            Sounds.play('slap.ogg')
            log.debug("board after drop:\n%s", str(self.game))

    def handle_captured(self, loc):
        captured_pieces = [p for p in self.pieces if p.location == loc]
        if captured_pieces:
            self.pieces.remove(captured_pieces[0])

    def _board_space_setup(self):
        """ initialize board state """
        for col, row in self.game.usable_positions():
            self.board_spaces.add(Square(row, col))

    def _screen_init(self):
        """ Initialise screen """
        self.screen = pygame.display.set_mode(SCREEN_RES)
        pygame.display.set_caption(self.window_title)
        return self.screen

    def _get_background(self):
        result = pygame.Surface(self.screen.get_size())
        (bg_img, bg_rect) = Images.load('marble-board.jpg')
        result.blit(bg_img, bg_rect)
        return result.convert(), bg_rect

    def _clear_items(self):
        self.fg_text.clear(self.screen, self.background)
        self.piece_selected.clear(self.screen, self.background)
        self.pieces.clear(self.screen, self.background)
        self.bg_text.clear(self.screen, self.background)

    def _quit(self):
        log.debug('quitting')
        self.game.client.quit()
        self.game_running = False

    def _select_piece(self, event):
        # select the piece by seeing if the piece collides with cursor
        self.piece_selected.add(piece for piece in self.pieces
                                if piece.rect.collidepoint(event.pos)
                                and piece.player == self.player
                                and piece.player == self.game.turn)
        # Capture piece's original position (at center) to determine move on drop
        if len(self.piece_selected) > 0:
            # Assumed: starting a move
            pygame.event.set_grab(True)
            self.pieces.remove(self.piece_selected)
            self.current_piece_position = (self.piece_selected.sprite.rect.centerx,
                                           self.piece_selected.sprite.rect.centery)
            log.debug('grabbing input, picked up piece at %s', self.current_piece_position)
            Sounds.play('slide.ogg')

    def _drag_piece(self):
        #  Until button is let go, move the piece with the mouse position
        if self.log_drag:
            log.debug('dragging')
        rect = self.piece_selected.sprite.rect
        rect.centerx, rect.centery = pygame.mouse.get_pos()
        if self.log_drag:
            log.debug('updated piece to %s', pygame.mouse.get_pos())

    def _reset_selected_piece(self):
        self.piece_selected.sprite.update_from_board()
        Sounds.play('slap.ogg')
        log.debug("board after drop:\n%s", str(self.game))

    def _drop_piece(self, event):
        if pygame.event.get_grab():
            pygame.event.set_grab(False)
            log.debug('releasing input')

            # center the piece on the valid space; if it is not touching a space, return it to its original position
            space_selected = [space for space in self.board_spaces if space.collidepoint(event.pos)]

            if self.piece_selected and space_selected:
                log.debug('dropped a piece')
                piece, space = self.piece_selected.sprite, space_selected[0]
                try:
                    self.game.move(piece.location, (space.col, space.row))
                except InvalidMoveException as ce:
                    log.debug(ce)
                    self._reset_selected_piece()
            else:
                log.debug('dropped on unplayable game space')
                self._reset_selected_piece()

            # Add piece back to stationary set
            self.pieces.add(self.piece_selected)

            # clean up for the next selected piece
            self.piece_selected.empty()

    def _draw_items(self):
        self.bg_text.draw(self.screen)
        self.pieces.draw(self.screen)
        self.piece_selected.draw(self.screen)
        self.fg_text.draw(self.screen)

    def _update(self):
        self.game.update()

        self.fps_text.text = "%4.1f fps" % self.fps_clock.get_fps()

        if self.player:
            self.player_text.text = "Your pieces are %s" % self.player

        if self.game.turn not in players:
            self.turn_text.text = "Waiting for player"
        else:
            if self.player == self.game.turn:
                self.turn_text.text = "Your turn"
            else:
                self.turn_text.text = "%s's turn" % self.game.turn.title()

        if self.game.winner():
            self.turn_text.text = ''
            self.winner_text.text = "%s wins!" % self.game.winner().title()
        else:
            self.winner_text.text = ''

        if not self.piece_selected and self.player == self.game.turn:
            highlight_player = self.game.turn
        else:
            highlight_player = None
        self.pieces.update(highlight_player)
        self.piece_selected.update(self.game.turn)
        self.bg_text.update()
        self.fg_text.update()

    def run(self):

        log.debug('pre-initializing sound')
        mixer.pre_init(buffer=32)

        log.debug('starting game')
        pygame.init()

        log.debug('initializing screen')
        self.screen = self._screen_init()

        log.debug('getting font')
        self.font = pygame.font.Font(None, 36)

        log.debug('loading background')
        self.background, self.background_rect = self._get_background()

        log.debug('setting up drop locations')
        self._board_space_setup()

        log.debug('building text')
        bg_rect = self.background_rect

        class FPSText(Text):
            def update(self, *args):
                Text.update(self, *args)
                self.rect.right, self.rect.bottom = bg_rect.right, bg_rect.bottom

        self.fps_text = FPSText('', self.font, WHITE)
        if self.show_fps:
            self.fg_text.add(self.fps_text)

        class TurnText(Text):
            def update(self, *args):
                Text.update(self, *args)
                self.rect.centerx, self.rect.centery = bg_rect.centerx, bg_rect.centery

        self.turn_text = TurnText('', self.font, WHITE)
        self.bg_text.add(self.turn_text)

        class WinnerText(Text):
            def update(self, *args):
                Text.update(self, *args)
                self.rect.centerx, self.rect.centery = bg_rect.centerx, bg_rect.centery

        self.winner_text = WinnerText('', self.font, WHITE)
        self.fg_text.add(self.winner_text)

        class PlayerText(Text):
            def update(self, *args):
                Text.update(self, *args)
                self.rect.centerx, self.rect.bottom = bg_rect.centerx, bg_rect.bottom

        self.player_text = PlayerText('', pygame.font.Font(None, 24), WHITE)
        self.bg_text.add(self.player_text)

        class GameIdText(Text):
            def update(self, *args):
                Text.update(self, *args)
                self.rect.centerx, self.rect.top = bg_rect.centerx, bg_rect.top + (0.25 * self.font.get_height())

        self.game_id_text = GameIdText('', pygame.font.Font(None, 20), WHITE)
        self.bg_text.add(self.game_id_text)

        log.debug('drawing initial content to screen')
        self.screen.blit(self.background, ORIGIN)
        pygame.display.flip()

        self.piece_selected = GroupSingle()
        self.current_piece_position = ORIGIN

        self.fps_clock = Clock()

        # Event loop
        while self.game_running:

            self._clear_items()

            for event in pygame.event.get():

                if event.type == QUIT:
                    self._quit()

                if event.type == MOUSEBUTTONDOWN:     # select a piece
                    log.debug('mouse pressed')
                    self._select_piece(event)

                if event.type == MOUSEBUTTONUP:     # let go of a piece
                    log.debug('mouse released')
                    self._drop_piece(event)

                if pygame.event.get_grab():          # drag selected piece around
                    self._drag_piece()

            self._update()

            self._draw_items()

            self.fps_clock.tick(60)  # Waits to maintain 60 fps

            # TODO: Use display.update instead
            pygame.display.flip()

        log.debug('finishing game loop')


class ServerFinder:

    def __init__(self):
        self.servers = []

    @staticmethod
    def _get_address(zc, type, name):
        info = zc.getServiceInfo(type, name)
        address = dict(ip=inet_ntoa(info.address), port=info.port)
        return address

    def removeService(self, zc, type, name):
        log.debug("del service type: '%s', name: '%s'" % (type, name))
        self.servers.remove(self._get_address(zc, type, name))

    def addService(self, zc, type, name):
        log.debug("add service type: '%s', name: '%s'" % (type, name))
        self.servers.append(self._get_address(zc, type, name))
        if self.servers:
            log.debug('shutting down auto-discovery')
            zc.close()

    def find_servers(self, timeout=AUTO_DISCOVERY_WAIT):
        log.info('searching for game servers')
        service_browser = ServiceBrowser(Zeroconf(), '%s.local.' % AUTO_DISCOVERY_TYPE, self)
        service_browser.join(timeout=timeout)
        return self.servers


if __name__ == '__main__':

    from argparse import ArgumentParser

    def parse_arguments():
        arg_p = ArgumentParser(description='A network-based checkers client')
        arg_p.add_argument('--host', help='server host')
        arg_p.add_argument('--port', help='server port', type=int)
        arg_p.add_argument('--log-level', help='diagnostic logging level', choices=['DEBUG', 'INFO'], default='INFO')
        arg_p.add_argument('--log-drag', help='log drag events', action='store_true', default=False)
        arg_p.add_argument('--show-fps', help='show frame rate', action='store_true', default=False)
        arg_p.add_argument('--spectate', help='attempt to auto-spectate', action='store_true', default=False)
        return arg_p.parse_args()

    def configure_logging(level):
        log.basicConfig(level=log.getLevelName(level))

    def start_game(**kwargs):
        game = Game(**kwargs)
        game.run()

    args = parse_arguments()
    configure_logging(args.log_level)
    game_args = dict(log_drag=args.log_drag, show_fps=args.show_fps, spectate=args.spectate)

    if not (args.host or args.port):
        services = ServerFinder().find_servers()
        if services:
            game_args.update(services[0])
        else:
            log.info('failed to locate a checkers server')
            sys.exit(1)
    else:
        if args.host:
            game_args['ip'] = args.host
        elif args.port:
            game_args['port'] = args.port

    start_game(**game_args)
