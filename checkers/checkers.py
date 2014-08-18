#!/usr/bin/env python
#
# Clare's Checkers
# A simple checkers game
#
# Released under the GNU General Public License

import os
import sys
import logging as log
import pygame
from pygame.sprite import Sprite, RenderUpdates, GroupSingle
from pygame.constants import QUIT, MOUSEBUTTONDOWN, MOUSEBUTTONUP
from pygame.time import Clock
from internals import Board, Piece, RED, BLACK, InvalidMoveException

log.basicConfig(level=log.INFO)

brown = (143, 96, 40)
white = (255, 255, 255)

global tile_width
global board_dim
global screen_res
global window_title

tile_width = 75
board_dim = 8
screen_res = (600, 600)
window_title = 'Checkers'
origin = (0, 0)
show_fps = False

log.debug('starting game')

game = Board(board_dim)


def load_png(name, colorkey=None):
    """ Load image and return image object"""
    fullname = os.path.join('../images', name)
    log.debug('loading png: %s', fullname)
    try:
        image = pygame.image.load(fullname)
        if colorkey:
            image.set_colorkey(brown)   # make all brown transparent
        if image.get_alpha() is None:
            image = image.convert()
        else:
            image = image.convert_alpha()
    except pygame.error, message:
            log.exception('failed to load image %s: %s', fullname, message)
            raise SystemExit
    return image, image.get_rect()


class CheckerPiece(Piece, Sprite):

    """A sprite for a single piece."""

    def __init__(self, player):
        Sprite.__init__(self)
        Piece.__init__(self, player)
        screen = pygame.display.get_surface()
        self.area = screen.get_rect()
        if player == RED:
            self.image, self.rect = load_png('red-piece.png', brown)
        elif player == BLACK:
            self.image, self.rect = load_png('black-piece.png', brown)
        else:
            print 'Invalid player name: ', player
            raise SystemExit
        self.player = player
        self.type = "man"

    def update_from_board(self):

        if self.king and self.type != "king":
            # This needs to happen before the rect update below because rect is replaced by image load
            self.type = "king"
            if self.player == RED:
                self.image, self.rect = load_png('red-piece-king.png', brown)
            elif self.player == BLACK:
                self.image, self.rect = load_png('black-piece-king.png', brown)

        self.rect.centerx = tile_width * self.location[0] + (tile_width / 2)
        self.rect.centery = tile_width * self.location[1] + (tile_width / 2)

    def update(self, position):
        self.rect.centerx, self.rect.centery = position


class BoardSpace(Sprite):

    """A sprite abstraction for game board spaces."""

    def __init__(self, initial_position, color, row, col):
        Sprite.__init__(self)
        screen = pygame.display.get_surface()
        self.area = screen.get_rect()
        self.color = color
        self.row = row
        self.col = col
        if color == "brown":
            self.image, self.rect = load_png('brown-space.png')
        elif color == "tan":
            self.image, self.rect = load_png('tan-space.png')
        else:
            print 'Invalid space color: ', color
            raise SystemExit
        self.rect.topleft = initial_position


def board_setup(**kwargs):
    brown_spaces = kwargs.get('brown_spaces')

    """ initialize board state """
    # Initialize board spaces (they are sprites)
    # A better data structure would simplify this...
    for col, row in game.usable_positions():
        loc = tile_width * col, tile_width * row
        brown_spaces.add(BoardSpace(loc, "brown", row, col))


def screen_init():
    """ Initialise screen """
    pygame.init()
    screen = pygame.display.set_mode(screen_res)
    pygame.display.set_caption(window_title)
    return screen


def get_background(screen):
    result = pygame.Surface(screen.get_size()).convert()
    (b_img, _) = load_png('brown-space.png')
    (t_img, _) = load_png('tan-space.png')
    usable = game.usable_positions()
    for x, y in [(x, y) for y in xrange(0, board_dim) for x in xrange(0, board_dim)]:
        tile_x, tile_y = x * tile_width, y * tile_width
        if (x, y) in usable:
            result.blit(b_img, (tile_x, tile_y))
        else:
            result.blit(t_img, (tile_x, tile_y))
    return result.convert()


def main():

    log.debug('initializing screen')

    # Fill background
    screen = screen_init()
    background = get_background(screen)
    background_rect = background.get_rect()

    font = pygame.font.Font(None, 36)

    # Initialize Game Groups
    brown_spaces = RenderUpdates()
    pieces = RenderUpdates()

    # board setup
    log.debug('building initial game board')
    board_setup(brown_spaces=brown_spaces)

    # Intialize playing pieces
    log.debug('initializing game pieces')
    for player, x, y in game.start_positions():
        new_piece = CheckerPiece(player)
        game.add_piece(new_piece, (x, y))
        new_piece.update_from_board()
        pieces.add(new_piece)

    # Blit everything to the screen
    screen.blit(background, origin)
    pygame.display.flip()

    piece_selected = GroupSingle()
    space_selected = GroupSingle()
    global currentpiece_position
    currentpiece_position = origin

    fps_clock = Clock()

    def get_fps_text():
        surface = font.render("%4.1f F/S" % fps_clock.get_fps(), 1, white)
        rect = surface.get_rect()
        rect.right, rect.bottom = background_rect.right, background_rect.bottom
        return surface, rect

    if show_fps:
        global fps_text, fps_rect
        fps_text, fps_rect = get_fps_text()

    def clear_items():
        if show_fps:
            screen.blit(background, fps_rect, area=fps_rect)
        piece_selected.clear(screen, background)
        pieces.clear(screen, background)
        
    def draw_items():
        global fps_text, fps_rect
        pieces.draw(screen)
        piece_selected.draw(screen)
        fps_clock.tick(60)  # Waits to maintain 60 fps
        if show_fps:
            fps_text, fps_rect = get_fps_text()
            screen.blit(fps_text, fps_rect)

    def quit_game():
        log.debug('quitting')
        sys.exit()

    def select_piece(e):
        global currentpiece_position
        # select the piece by seeing if the piece collides with cursor
        piece_selected.add(piece for piece in pieces if piece.rect.collidepoint(e.pos))
        # Capture piece's original position (at center) to determine move on drop
        if len(piece_selected) > 0:
            # Assumed: starting a move
            pygame.event.set_grab(True)
            pieces.remove(piece_selected)
            currentpiece_position = (piece_selected.sprite.rect.centerx, piece_selected.sprite.rect.centery)
            log.debug('grabbing input, picked up piece at %s', currentpiece_position)

    def drag_piece():
        #  Until botton is let go, move the piece with the mouse position
        piece_selected.update(pygame.mouse.get_pos())
        log.debug('updated piece to %s', pygame.mouse.get_pos())

    def drop_piece(e):
        if pygame.event.get_grab():
            pygame.event.set_grab(False)
            log.debug('releasing input')

            # center the piece on the valid space; if it is not touching a space, return it to its original position
            space_selected.add(space for space in brown_spaces if space.rect.collidepoint(e.pos))

            if piece_selected and space_selected:
                log.debug('dropped a piece')
                piece, space = piece_selected.sprite, space_selected.sprite
                try:
                    captured = game.move(piece.location, (space.col, space.row))
                    if captured:
                        pieces.remove(captured)
                except InvalidMoveException as ce:
                    log.debug(ce)
                log.debug(str(game))

            piece_selected.sprite.update_from_board()

            # Add piece back to stationary set
            pieces.add(piece_selected)
            
            # clean up for the next selected piece
            piece_selected.empty()
            space_selected.empty()

    def draw_winner():
        winner = game.winner()
        if winner:
            text = font.render("The winner was %s!" % winner, 1, white)
            textpos = text.get_rect()
            textpos.centerx = background.get_rect().centerx
            textpos.top = 100
            screen.blit(text, textpos)

    # Event loop
    while True:

        clear_items()

        for event in pygame.event.get():

            if event.type == QUIT:
                quit_game()

            if event.type == MOUSEBUTTONDOWN:     # select a piece
                log.debug('mouse pressed')
                select_piece(event)

            if event.type == MOUSEBUTTONUP:     # let go of a piece
                log.debug('mouse released')
                drop_piece(event)

            if pygame.event.get_grab():          # drag selected piece around
                log.debug('dragging')
                drag_piece()

        draw_items()

        draw_winner()

        # TODO: Use display.update instead
        pygame.display.flip()

if __name__ == '__main__':
    main()
