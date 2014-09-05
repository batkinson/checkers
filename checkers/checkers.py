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
        self.current_piece_position = ORIGIN
        self.screen = None
        self.fps_clock = None
        self.font = None
        self.font_rect = None
        self.background = None
        self.background_rect = None
        self.fps_text = None
        self.fps_rect = None
        self.winner_text = None
        self.winner_rect = None
        self.turn_text = None
        self.turn_rect = None

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

    def _get_fps_text(self):
        fps_text = self.font.render("%4.1f fps" % self.fps_clock.get_fps(), True, WHITE)
        rect = fps_text.get_rect()
        rect.right, rect.bottom = self.background_rect.right, self.background_rect.bottom
        return fps_text, rect

    def _draw_fps(self):
        if self.show_fps:
            self.fps_text, self.fps_rect = self._get_fps_text()
            self.screen.blit(self.fps_text, self.fps_rect)

    def _clear_fps(self):
        if self.show_fps:
            self.screen.blit(self.background, self.fps_rect, area=self.fps_rect)

    def _clear_items(self):
        self._clear_fps()
        self._clear_winner()
        self.piece_selected.clear(self.screen, self.background)
        self._clear_turn()
        self.pieces.clear(self.screen, self.background)

    def _draw_winner(self):
        winner = self.game.winner()
        if winner:
            self.winner_text = self.font.render("%s wins!" % winner.title(), True, WHITE)
            winner_rect = self.winner_text.get_rect()
            winner_rect.centerx = self.background.get_rect().centerx
            winner_rect.top = 100
            self.winner_rect = winner_rect
            self.screen.blit(self.winner_text, winner_rect)

    def _clear_winner(self):
        winner = self.game.winner()
        if winner:
            self.screen.blit(self.background, self.winner_rect, area=self.winner_rect)

    def _draw_turn(self):
        if not self.game.winner():
            msg = None
            if self.game.turn not in players:
                msg = "Waiting for player"
            else:
                if self.player == self.game.turn:
                    msg = "Your turn"
                else:
                    msg = "%s's turn" % self.game.turn.title()
            turn_text = self.font.render(msg, True, WHITE)
            turn_rect = turn_text.get_rect()
            turn_rect.centerx, turn_rect.centery = self.background_rect.centerx, self.background_rect.centery
            self.screen.blit(turn_text, turn_rect)
        else:
            turn_text, turn_rect = None, None
        self.turn_text, self.turn_rect = turn_text, turn_rect

    def _clear_turn(self):
        if self.turn_rect:
            self.screen.blit(self.background, self.turn_rect, area=self.turn_rect)

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
                    captured = self.game.move(piece.location, (space.col, space.row))
                    if captured:
                        self.pieces.remove(captured)
                    Sounds.play('slap.ogg')
                except InvalidMoveException as ce:
                    log.debug(ce)
                log.debug("board after drop:\n%s", str(self.game))

            self.piece_selected.sprite.update_from_board()

            # Add piece back to stationary set
            self.pieces.add(self.piece_selected)

            # clean up for the next selected piece
            self.piece_selected.empty()

    def _draw_items(self):
        self.pieces.draw(self.screen)
        self._draw_turn()
        self.piece_selected.draw(self.screen)
        self._draw_winner()
        self._draw_fps()

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
        self.background, self.background_rect= self._get_background()

        log.debug('building initial game board')
        self._board_setup(brown_spaces=self.board_spaces)

        log.debug('drawing initial content to screen')
        self.screen.blit(self.background, ORIGIN)
        pygame.display.flip()

        self.piece_selected = GroupSingle()
        self.current_piece_position = ORIGIN

        self.fps_clock = Clock()

        self._draw_fps()

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

            self.game.update()

            self._draw_items()

            self.fps_clock.tick(60)  # Waits to maintain 60 fps

            # TODO: Use display.update instead
            pygame.display.flip()

if __name__ == '__main__':
    game = None
    log_level = log.INFO
    if len(sys.argv) > 2:
        ip = sys.argv[1]
        port = int(sys.argv[2])
        game = Game(log_level=log_level, ip=ip, port=port)
    else:
        game = Game(log_level=log_level)
    game.run()
