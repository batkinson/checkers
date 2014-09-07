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
from netclient import NetBoard, StatusHandler

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
    def load(cls, name, color_key=None):
        """ Load image and return image object"""
        fullname = os.path.join('..', 'images', name)
        if fullname in cls.image_cache:
            return cls.image_cache[fullname], cls.image_cache[fullname].get_rect()
        try:
            log.debug('loading: %s', fullname)
            image = pygame.image.load(fullname)
            if color_key:
                image.set_colorkey(color_key)   # make all brown transparent
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
        screen = pygame.display.get_surface()
        self.area = screen.get_rect()
        if player == RED:
            self.image, self.rect = Images.load('red-piece.png')
        elif player == BLACK:
            self.image, self.rect = Images.load('black-piece.png')
        else:
            print 'Invalid player name: ', player
            raise SystemExit
        self.player = player
        self.type = "man"

    def update_from_board(self):

        if self.king:
            if self.player == RED:
                self.image, _ = Images.load('red-piece-king.png')
            elif self.player == BLACK:
                self.image, _ = Images.load('black-piece-king.png')

        self.rect.centerx, self.rect.centery = [game_to_screen(v) for v in self.location]

    def update(self, position):
        self.rect.centerx, self.rect.centery = position


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

    def __init__(self, title='Checkers', log_level=log.INFO, log_drag=False, show_fps=False, ip='127.0.0.1', port=5000):
        log.basicConfig(level=log_level)
        self.player = None
        self.log_drag = log_drag
        self.show_fps = show_fps
        self.window_title = title
        self.game = NetBoard(handler=self, ip=ip, port=port)
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

    def handle_list(self, game_list):
        if game_list:
            self.game.client.join(game_list[0])
        else:
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

    def handle_captured(self, loc):
        captured_pieces = [p for p in self.pieces if p.location == loc]
        if captured_pieces:
            self.pieces.remove(captured_pieces[0])

    def _board_setup(self, **kwargs):
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
        sys.exit(0)

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
        self.piece_selected.update(pygame.mouse.get_pos())
        if self.log_drag:
            log.debug('updated piece to %s', pygame.mouse.get_pos())

    def _reset_selected_piece(self):
        self.piece_selected.sprite.update_from_board()
        Sounds.play('slap.ogg')

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
                self._reset_selected_piece()

            log.debug("board after drop:\n%s", str(self.game))

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

        log.debug('building initial game board')
        self._board_setup(brown_spaces=self.board_spaces)

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

        log.debug('drawing initial content to screen')
        self.screen.blit(self.background, ORIGIN)
        pygame.display.flip()

        self.piece_selected = GroupSingle()
        self.current_piece_position = ORIGIN

        self.fps_clock = Clock()

        # Event loop
        while True:

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
                    if self.log_drag:
                        log.debug('dragging')
                    self._drag_piece()

            self._update()

            self._draw_items()

            self.fps_clock.tick(60)  # Waits to maintain 60 fps

            # TODO: Use display.update instead
            pygame.display.flip()

if __name__ == '__main__':
    game = None
    log_level = log.INFO
    show_fps = False
    if len(sys.argv) > 2:
        ip = sys.argv[1]
        port = int(sys.argv[2])
        game = Game(show_fps=show_fps, log_level=log_level, ip=ip, port=port)
    else:
        game = Game(show_fps=show_fps, log_level=log_level)
    game.run()
