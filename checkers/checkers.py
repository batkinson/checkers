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
from pygame.constants import QUIT, MOUSEBUTTONDOWN, MOUSEBUTTONUP
from pygame.time import Clock
from internals import Checkers, RED, BLACK

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

log.debug('starting game')

game = Checkers(board_dim)


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


class CheckerPiece(pygame.sprite.Sprite):

    """A sprite for a single piece."""

    def __init__(self, player, (centerx, centery)):
        pygame.sprite.Sprite.__init__(self)
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
        self.rect.centerx = centerx
        self.rect.centery = centery
        self.type = "man"

    def king(self):
        self.type = "king"
        if self.player == RED:
            self.image, self.rect = load_png('red-piece-king.png', brown)
        elif self.player == BLACK:
            self.image, self.rect = load_png('black-piece-king.png', brown)

    def update(self, position):
        self.rect.centerx = position[0]
        self.rect.centery = position[1]


class BoardSpace(pygame.sprite.Sprite):

    """A sprite abstraction for game board spaces."""

    def __init__(self, initial_position, color, row, col):
        pygame.sprite.Sprite.__init__(self)
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
    for row, col in [(r, c) for r in range(board_dim) for c in range(board_dim)]:
            top, left = tile_width * row, tile_width * col
            odd_row, odd_col = row % 2, col % 2
            even_row, even_col = not odd_row, not odd_col
            if (even_row and odd_col) or (odd_row and even_col):
                brown_spaces.add(BoardSpace((left, top), "brown", row, col))


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
    usable = set(game.usable_positions())
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
    brown_spaces = pygame.sprite.RenderUpdates()
    pieces = pygame.sprite.RenderUpdates()

    # board setup
    log.debug('building initial game board')
    board_setup(brown_spaces=brown_spaces)

    # Intialize playing pieces
    log.debug('initializing game pieces')
    for player, col, row in game:
        top, left = tile_width*row, tile_width*col
        new_piece = CheckerPiece(player, (left+(tile_width/2), top+(tile_width/2)))
        pieces.add(new_piece)

    # Blit everything to the screen
    screen.blit(background, origin)
    pygame.display.flip()

    piece_selected = pygame.sprite.GroupSingle()
    space_selected = pygame.sprite.GroupSingle()
    global currentpiece_position
    currentpiece_position = origin

    fps_clock = Clock()

    def get_fps_text():
        surface = font.render("%4.1f F/S" % fps_clock.get_fps(), 1, white)
        rect = surface.get_rect()
        rect.right, rect.bottom = background_rect.right, background_rect.bottom
        return surface, rect

    global fps_text, fps_rect
    fps_text, fps_rect = get_fps_text()

    def clear_items():
        screen.blit(background, fps_rect, area=fps_rect)
        piece_selected.clear(screen, background)
        pieces.clear(screen, background)
        
    def draw_items():
        global fps_text, fps_rect
        pieces.draw(screen)
        piece_selected.draw(screen)
        fps_clock.tick()
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

            log.debug('dropped a piece')

            # center the piece on the valid space; if it is not touching a space, return it to its original position
            space_selected.add(space for space in brown_spaces if space.rect.collidepoint(e.pos))
            pieces_there = [piece for piece in pieces if piece.rect.collidepoint(e.pos)]
            valid_move = piece_selected and space_selected and not pieces_there
            capture_piece = False

            # if piece is kinged, piece goes to (row-1 and (col+1 or col-1))
            #                OR (piece on (col-1, row-1) and piece goes to (col-2, row-2) -- capture piece
            #                OR (piece on (col+1, row-1) and piece goes to (col+2, row-2) -- capture piece
            #                OR piece goes to (row+1 and (col+1 or col-1))
            #                OR (piece on (col-1, row+1) and piece goes to (col-2, row+2) -- capture piece
            #                OR (piece on (col+1, row+1) and piece goes to (col+2, row+2) -- capture piece
            # else if piece is black, piece goes to (row+1 and (col+1 or col-1))
            #                OR (piece on (col-1, row+1) and piece goes to (col-2, row+2) -- capture piece
            #                OR (piece on (col+1, row+1) and piece goes to (col+2, row+2) -- capture piece
            # else if piece is red, piece goes to (row-1 and (col+1 or col-1))
            #                OR (piece on (col-1, row-1) and piece goes to (col-2, row-2) -- capture piece
            #                OR (piece on (col+1, row-1) and piece goes to (col+2, row-2) -- capture piece

            if valid_move:

                if piece_selected.sprite.type == "king":
                    # Kings can move forward and backwards
                    if space_selected.sprite.rect.collidepoint(currentpiece_position[0]-tile_width, currentpiece_position[1]-tile_width) \
                        or space_selected.sprite.rect.collidepoint(currentpiece_position[0]+tile_width, currentpiece_position[1]-tile_width):
                        pass
                    elif len([piece for piece in pieces if piece.rect.collidepoint(currentpiece_position[0]-tile_width, currentpiece_position[1]-tile_width)]) > 0\
                        and space_selected.sprite.rect.collidepoint(currentpiece_position[0]-2*tile_width, currentpiece_position[1]-2*tile_width):
                        capture_piece = True
                    elif len([piece for piece in pieces if piece.rect.collidepoint(currentpiece_position[0]+tile_width, currentpiece_position[1]-tile_width)]) > 0\
                            and space_selected.sprite.rect.collidepoint(currentpiece_position[0]+2*tile_width, currentpiece_position[1]-2*tile_width):
                        capture_piece = True
                    elif space_selected.sprite.rect.collidepoint(currentpiece_position[0]-tile_width, currentpiece_position[1]+tile_width) \
                        or space_selected.sprite.rect.collidepoint(currentpiece_position[0]+tile_width, currentpiece_position[1]+tile_width):
                        pass
                    elif len([piece for piece in pieces if piece.rect.collidepoint(currentpiece_position[0]-tile_width, currentpiece_position[1]+tile_width)]) > 0\
                            and space_selected.sprite.rect.collidepoint(currentpiece_position[0]-2*tile_width, currentpiece_position[1]+2*tile_width):
                        capture_piece = True
                    elif len([piece for piece in pieces if piece.rect.collidepoint(currentpiece_position[0]+tile_width, currentpiece_position[1]+tile_width)]) > 0\
                            and space_selected.sprite.rect.collidepoint(currentpiece_position[0]+2*tile_width, currentpiece_position[1]+2*tile_width):
                        capture_piece = True
                    else:
                        valid_move = False
                # Normal pieces (not kings) can only move towards opposing side
                elif (piece_selected.sprite.player == BLACK) and (len(space_selected) > 0):
                    if space_selected.sprite.rect.collidepoint(currentpiece_position[0]-tile_width, currentpiece_position[1]+tile_width) \
                        or space_selected.sprite.rect.collidepoint(currentpiece_position[0]+tile_width, currentpiece_position[1]+tile_width):
                        pass
                    elif len([piece for piece in pieces if piece.rect.collidepoint(currentpiece_position[0]-tile_width, currentpiece_position[1]+tile_width)]) > 0\
                            and space_selected.sprite.rect.collidepoint(currentpiece_position[0]-2*tile_width, currentpiece_position[1]+2*tile_width):
                        capture_piece = True
                    elif len([piece for piece in pieces if piece.rect.collidepoint(currentpiece_position[0]+tile_width, currentpiece_position[1]+tile_width)]) > 0\
                            and space_selected.sprite.rect.collidepoint(currentpiece_position[0]+2*tile_width, currentpiece_position[1]+2*tile_width):
                        capture_piece = True
                    else:
                        valid_move = False
                elif (piece_selected.sprite.player == RED) and (len(space_selected) > 0):
                    if space_selected.sprite.rect.collidepoint(currentpiece_position[0]-tile_width, currentpiece_position[1]-tile_width) \
                        or space_selected.sprite.rect.collidepoint(currentpiece_position[0]+tile_width, currentpiece_position[1]-tile_width):
                        pass
                    elif len([piece for piece in pieces if piece.rect.collidepoint(currentpiece_position[0]-tile_width, currentpiece_position[1]-tile_width)]) > 0\
                            and space_selected.sprite.rect.collidepoint(currentpiece_position[0]-2*tile_width, currentpiece_position[1]-2*tile_width):
                        capture_piece = True
                    elif len([piece for piece in pieces if piece.rect.collidepoint(currentpiece_position[0]+tile_width, currentpiece_position[1]-tile_width)]) > 0\
                            and space_selected.sprite.rect.collidepoint(currentpiece_position[0]+2*tile_width, currentpiece_position[1]-2*tile_width):
                        capture_piece = True
                    else:
                        valid_move = False
                else:
                    valid_move = False

            if valid_move:
                # king the piece if applicable
                if (piece_selected.sprite.player == RED and space_selected.sprite.row == 0) \
                    or (piece_selected.sprite.player == BLACK and space_selected.sprite.row == 7):
                    log.debug('kinged piece')
                    piece_selected.sprite.king()
                new_pos = (space_selected.sprite.rect.centerx, space_selected.sprite.rect.centery)
                piece_selected.update(new_pos)
                log.debug('valid move: dropped piece at new position %s', new_pos)
            else:
                piece_selected.update(currentpiece_position)
                log.debug('invalid move: dropped piece at original position %s', currentpiece_position)

            pieces.add(piece_selected)

            if capture_piece:
                # It seems this information is recomputed from above
                capture_piece_x = (space_selected.sprite.rect.centerx + currentpiece_position[0])/2
                capture_piece_y = (space_selected.sprite.rect.centery + currentpiece_position[1])/2
                log.debug('captured piece at %s', (capture_piece_x, capture_piece_y))
                pieces.remove(piece for piece in pieces if piece.rect.collidepoint(capture_piece_x, capture_piece_y))

            # clean up for the next selected piece
            piece_selected.empty()
            space_selected.empty()

    def draw_winner():
        # determine if someone has won yet
        # It seems this is two ops:
        #    Who is the game winner, if any
        #    Show the winner
        # Missing is ending game?
        red_pieces = 0
        black_pieces = 0
        for piece in pieces:
            if piece.player == RED:
                red_pieces += 1
            elif piece.player == BLACK:
                black_pieces += 1
        if red_pieces > 0 or black_pieces == 0:
            font = pygame.font.Font(None, 36)
            text = font.render("", 1, white)
            if red_pieces == 0:
                text = font.render("The black player won!", 1, white)
                print "The black player won!"
            elif black_pieces == 0:
                text = font.render("The red player won!", 1, white)
                print "The red player won!"
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
