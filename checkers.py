#!/usr/bin/env python
#
# Clare's Checkers
# A simple checkers game
#
# Released under the GNU General Public License

import pygame,os,math
from pygame.locals import *

brown = (143,96,40)
tile_width = 75

class CheckerPiece(pygame.sprite.Sprite):
    def __init__(self, player,(centerx,centery)):
        pygame.sprite.Sprite.__init__(self)
        screen = pygame.display.get_surface()
        self.area = screen.get_rect()
        if player == "red":
            self.image, self.rect = self.load_png('red-piece.png')
        elif player == "black":
            self.image, self.rect = self.load_png('black-piece.png')
        else:
            print 'Invalid player name: ', player
            raise SystemExit, message
        self.player = player
        self.rect.centerx = centerx
        self.rect.centery = centery
        self.type = "man"

    def load_png(self,name):
        """ Load image and return image object"""
        fullname = os.path.join('images', name)
        try:
            image = pygame.image.load(fullname)
            image.set_colorkey(brown)   # make all brown transparent
            if image.get_alpha() is None:
                image = image.convert()
            else:
                image = image.convert_alpha()
        except pygame.error, message:
                print 'Cannot load image: ', fullname
                raise SystemExit, message
        return image, image.get_rect()

    def king(self):
        self.type = "king"
        if self.player == "red":
            self.image, self.rect = self.load_png('red-piece-king.png')
        elif self.player == "black":
            self.image, self.rect = self.load_png('black-piece-king.png')

    def update(self,position):
        self.rect.centerx = position[0]
        self.rect.centery = position[1]

class BoardSpace(pygame.sprite.Sprite):
    def __init__(self,initial_position,color,row,col):
        pygame.sprite.Sprite.__init__(self)
        screen = pygame.display.get_surface()
        self.area = screen.get_rect()
        self.color = color
        self.row = row
        self.col = col
        if color == "brown":
            self.image, self.rect = self.load_png('brown-space.png')
        elif color == "tan":
            self.image, self.rect = self.load_png('tan-space.png')
        else:
            print 'Invalid space color: ', color
            raise SystemExit, message
        self.rect.topleft = initial_position

    def load_png(self,name):
        """ Load image and return image object"""
        fullname = os.path.join('images', name)
        try:
            image = pygame.image.load(fullname)
            if image.get_alpha() is None:
                image = image.convert()
            else:
                image = image.convert_alpha()
        except pygame.error, message:
                print 'Cannot load image: ', fullname
                raise SystemExit, message
        return image, image.get_rect()    

def main():
    # Initialise screen
    pygame.init()
    screen = pygame.display.set_mode((600, 600))
    pygame.display.set_caption('Checkers')

    # Fill background
    background = pygame.Surface(screen.get_size())
    background = background.convert()
    background.fill((255,255,255))

    # Initialize Game Groups
    brown_spaces = pygame.sprite.RenderUpdates()
    tan_spaces = pygame.sprite.RenderUpdates()
    pieces = pygame.sprite.RenderUpdates()

    # Set up board
    for row in range(8):
        for col in range(8):
            top = tile_width*row
            left = tile_width*col
            if not(row % 2) and (col % 2):
                brown_spaces.add(BoardSpace((left,top),"brown",row,col))
            elif not(row % 2) and not(col % 2):
                tan_spaces.add(BoardSpace((left,top),"tan",row,col))
            elif (row % 2) and not(col % 2):
                brown_spaces.add(BoardSpace((left,top),"brown",row,col))
            elif (row % 2) and (col % 2):
                tan_spaces.add(BoardSpace((left,top),"tan",row,col))

    # Set up checker pieces
    for row in range(8):
        for col in range(8):
            if row < 3:
                player = "black"
            elif row > 4:
                player = "red"
            if row < 3 or row > 4:
                top = tile_width*row
                left = tile_width*col
                if not(row % 2) and (col % 2):
                    pieces.add(CheckerPiece(player,(left+(tile_width/2),top+(tile_width/2))))
                elif (row % 2) and not(col % 2):
                    pieces.add(CheckerPiece(player,(left+(tile_width/2),top+(tile_width/2))))

    # Blit everything to the screen
    screen.blit(background, (0, 0))
    pygame.display.flip()

    # Event loop
    piece_selected = pygame.sprite.GroupSingle()
    space_selected = pygame.sprite.GroupSingle()
    currentpiece_position = (0,0)

    while True:
        pieces.clear(screen,background)
        brown_spaces.clear(screen,background)
        tan_spaces.clear(screen,background)

        for event in pygame.event.get():
            if event.type == QUIT:
                return
            if event.type == MOUSEBUTTONDOWN:     # select a piece
                piece_selected.add(piece for piece in pieces if piece.rect.collidepoint(event.pos))
                pygame.event.set_grab(1)
                if len(piece_selected) > 0:
                    currentpiece_position = (piece_selected.sprite.rect.centerx,piece_selected.sprite.rect.centery)
            if event.type == MOUSEBUTTONUP:     # let go of a piece
                # center the piece on the valid space; if it is not touching a space, return it to its original position
                space_selected.add(space for space in brown_spaces if space.rect.collidepoint(event.pos))
                pieces_there = [piece for piece in pieces if piece.rect.collidepoint(event.pos)]

                valid_move = (len(space_selected) > 0)
                valid_move = valid_move and (len(pieces_there) == 1)
                capture_piece = 0

                # if piece is kinged, piece goes to (row-1 and (col+1 or col-1))
                #                OR (piece on (col-1,row-1) and piece goes to (col-2,row-2) -- capture piece
                #                OR (piece on (col+1,row-1) and piece goes to (col+2,row-2) -- capture piece
                #                OR piece goes to (row+1 and (col+1 or col-1)) 
                #                OR (piece on (col-1,row+1) and piece goes to (col-2,row+2) -- capture piece
                #                OR (piece on (col+1,row+1) and piece goes to (col+2,row+2) -- capture piece
                # else if piece is black, piece goes to (row+1 and (col+1 or col-1)) 
                #                OR (piece on (col-1,row+1) and piece goes to (col-2,row+2) -- capture piece
                #                OR (piece on (col+1,row+1) and piece goes to (col+2,row+2) -- capture piece
                # else if piece is red, piece goes to (row-1 and (col+1 or col-1))
                #                OR (piece on (col-1,row-1) and piece goes to (col-2,row-2) -- capture piece
                #                OR (piece on (col+1,row-1) and piece goes to (col+2,row-2) -- capture piece

                if (len    (space_selected) > 0) and (len(piece_selected) > 0):            
                    if (piece_selected.sprite.type == "king"):
                        if space_selected.sprite.rect.collidepoint(currentpiece_position[0]-tile_width,currentpiece_position[1]-tile_width) \
                            or space_selected.sprite.rect.collidepoint(currentpiece_position[0]+tile_width,currentpiece_position[1]-tile_width):
                            valid_move = valid_move and 1
                        elif len([piece for piece in pieces if piece.rect.collidepoint(currentpiece_position[0]-tile_width,currentpiece_position[1]-tile_width)]) > 0\
                            and space_selected.sprite.rect.collidepoint(currentpiece_position[0]-2*tile_width,currentpiece_position[1]-2*tile_width):
                            capture_piece = 1
                        elif len([piece for piece in pieces if piece.rect.collidepoint(currentpiece_position[0]+tile_width,currentpiece_position[1]-tile_width)]) > 0\
                                and space_selected.sprite.rect.collidepoint(currentpiece_position[0]+2*tile_width,currentpiece_position[1]-2*tile_width):
                            capture_piece = 1
                        elif space_selected.sprite.rect.collidepoint(currentpiece_position[0]-tile_width,currentpiece_position[1]+tile_width) \
                            or space_selected.sprite.rect.collidepoint(currentpiece_position[0]+tile_width,currentpiece_position[1]+tile_width):
                            valid_move = valid_move and 1
                        elif len([piece for piece in pieces if piece.rect.collidepoint(currentpiece_position[0]-tile_width,currentpiece_position[1]+tile_width)]) > 0\
                                and space_selected.sprite.rect.collidepoint(currentpiece_position[0]-2*tile_width,currentpiece_position[1]+2*tile_width):
                            capture_piece = 1
                        elif len([piece for piece in pieces if piece.rect.collidepoint(currentpiece_position[0]+tile_width,currentpiece_position[1]+tile_width)]) > 0\
                                and space_selected.sprite.rect.collidepoint(currentpiece_position[0]+2*tile_width,currentpiece_position[1]+2*tile_width):
                            capture_piece = 1
                        else:
                            valid_move = 0
                    elif (piece_selected.sprite.player == "black") and (len(space_selected) > 0):
                        if space_selected.sprite.rect.collidepoint(currentpiece_position[0]-tile_width,currentpiece_position[1]+tile_width) \
                            or space_selected.sprite.rect.collidepoint(currentpiece_position[0]+tile_width,currentpiece_position[1]+tile_width):
                            valid_move = valid_move and 1
                        elif len([piece for piece in pieces if piece.rect.collidepoint(currentpiece_position[0]-tile_width,currentpiece_position[1]+tile_width)]) > 0\
                                and space_selected.sprite.rect.collidepoint(currentpiece_position[0]-2*tile_width,currentpiece_position[1]+2*tile_width):
                            capture_piece = 1
                        elif len([piece for piece in pieces if piece.rect.collidepoint(currentpiece_position[0]+tile_width,currentpiece_position[1]+tile_width)]) > 0\
                                and space_selected.sprite.rect.collidepoint(currentpiece_position[0]+2*tile_width,currentpiece_position[1]+2*tile_width):
                            capture_piece = 1
                        else:
                            valid_move = 0
                    elif (piece_selected.sprite.player == "red") and (len(space_selected) > 0):
                        if space_selected.sprite.rect.collidepoint(currentpiece_position[0]-tile_width,currentpiece_position[1]-tile_width) \
                            or space_selected.sprite.rect.collidepoint(currentpiece_position[0]+tile_width,currentpiece_position[1]-tile_width):
                            valid_move = valid_move and 1
                        elif len([piece for piece in pieces if piece.rect.collidepoint(currentpiece_position[0]-tile_width,currentpiece_position[1]-tile_width)]) > 0\
                                and space_selected.sprite.rect.collidepoint(currentpiece_position[0]-2*tile_width,currentpiece_position[1]-2*tile_width):
                            capture_piece = 1
                        elif len([piece for piece in pieces if piece.rect.collidepoint(currentpiece_position[0]+tile_width,currentpiece_position[1]-tile_width)]) > 0\
                                and space_selected.sprite.rect.collidepoint(currentpiece_position[0]+2*tile_width,currentpiece_position[1]-2*tile_width):
                            capture_piece = 1
                        else:
                            valid_move = 0
                    else:
                        valid_move = 0

                if valid_move:
                    # king the piece if applicable
                    if (piece_selected.sprite.player == "red" and space_selected.sprite.row == 0) \
                        or (piece_selected.sprite.player == "black" and space_selected.sprite.row == 7):
                        piece_selected.sprite.king()
                    piece_selected.update((space_selected.sprite.rect.centerx,space_selected.sprite.rect.centery))
                else:
                    piece_selected.update(currentpiece_position)

                if capture_piece:
                    capture_piece_x = (space_selected.sprite.rect.centerx + currentpiece_position[0])/2
                    capture_piece_y = (space_selected.sprite.rect.centery + currentpiece_position[1])/2
                    pieces.remove(piece for piece in pieces if piece.rect.collidepoint(capture_piece_x,capture_piece_y))

                # clean up for the next selected piece
                pygame.event.set_grab(0)
                piece_selected.empty()
                space_selected.empty()

            if pygame.event.get_grab():          # drag selected piece around
                piece_selected.update(pygame.mouse.get_pos())

        brown_spaces.draw(screen)
        tan_spaces.draw(screen)
        pieces.draw(screen)

        # determine if someone has won yet
        red_pieces = 0
        black_pieces = 0
        for piece in pieces:
            if piece.player == "red":
                red_pieces = red_pieces + 1
            elif piece.player == "black":
                black_pieces = black_pieces + 1
        if red_pieces > 0 or black_pieces == 0:
            font = pygame.font.Font(None, 36)
            text = font.render("", 1, (255, 255, 255))
            if red_pieces == 0:
                text = font.render("The black player won!", 1, (255, 255, 255))
                print "The black player won!"
            elif black_pieces == 0:
                text = font.render("The red player won!", 1, (255, 255, 255))
                print "The red player won!"
            textpos = text.get_rect()
            textpos.centerx = background.get_rect().centerx
            textpos.top = 100
            screen.blit(text, textpos)

        pygame.display.flip()

if __name__ == '__main__': main()
