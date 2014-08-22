
RED = "red"
BLACK = "black"

players = [BLACK, RED]
opponent = {BLACK: RED, RED: BLACK}


class CheckersException(Exception):

    """The base exception type for the chess game."""

    def __init__(self, message):
        Exception.__init__(self, message)


class InvalidMoveException(CheckersException):

    """Represents when an attempted move is invalid."""

    def __init__(self, message):
        CheckersException.__init__(self, message)


class InvalidPlacementException(CheckersException):

    """Represents an invalid placement of a piece on the board."""

    def __init__(self, message):
        CheckersException.__init__(self, message)


class Piece():

    def __init__(self, player):
        if player not in [BLACK, RED]:
            raise CheckersException("invalid player %s" % player)
        self.player = player
        self.king = False
        self.board = None
        self.location = None

    def __str__(self):
        p = self.player[:1]
        if self.king:
            return p.upper()
        return p


class Board:

    def __init__(self, dim=8):
        """Create initial game state for normal checkers game."""
        self.dim = dim
        self._neutral_rows = 2
        self._usable_positions = set([(x, y) for y in xrange(0, self.dim) for x in xrange((y + 1) % 2, self.dim, 2)])

        # Pre-compute valid moves
        self._moves = {BLACK: {}, RED: {}}
        self._king_moves = {}
        self._jumps = {BLACK: {}, RED: {}}
        self._king_jumps = {}
        self._captures = {}
        self._init_moves()

        # Mutable data
        self._player_pieces = {BLACK: set(), RED: set()}
        self._loc_pieces = {}
        self.turn = BLACK
        self.last_jumped_to = None

    def _init_moves(self):

        for pos in self.usable_positions():

            pos_x, pos_y = pos

            # Initialize sets for position
            for player in [RED, BLACK]:
                self._moves[player][pos] = set()
                self._jumps[player][pos] = set()
            self._king_moves[pos] = set()
            self._king_jumps[pos] = set()

            # compute valid moves, jumps and captures for normal pieces by player
            for player, mov_off_y, jmp_off_y in [(BLACK, 1, 2), (RED, -1, -2)]:
                for mov_off_x, jmp_off_x in [(-1, -2), (1, 2)]:
                    mov_loc, jmp_loc = (pos_x + mov_off_x, pos_y + mov_off_y), (pos_x + jmp_off_x, pos_y + jmp_off_y)
                    if mov_loc in self.usable_positions():
                        self._moves[player][pos].add(mov_loc)
                    if jmp_loc in self.usable_positions():
                        self._jumps[player][pos].add(jmp_loc)
                        self._captures[(pos, jmp_loc)] = mov_loc

            self._king_moves[pos] = self._moves[BLACK][pos] | self._moves[RED][pos]
            self._king_jumps[pos] = self._jumps[BLACK][pos] | self._jumps[RED][pos]

    def add_piece(self, piece, location):
        """Adds a new Piece to this board. Raises a CheckersException if placement is invalid."""
        if not isinstance(piece, Piece):
            raise CheckersException('can only add Pieces')
        if not self._valid_placement(piece, location):
            raise InvalidPlacementException('can not place piece at %s' % location)
        self[location] = piece

    def _valid_placement(self, piece, location):
        """Returns true if the specified piece can be placed at the specified location."""
        return location in self._usable_positions and not location in self

    def start_positions(self):
        """Returns a list of (player,x,y) tuples for start positions"""
        black_positions = [(BLACK, x, y) for (x, y) in self._usable_positions if y < self._player_rows()]
        red_positions = [(RED, x, y) for (x, y) in self._usable_positions if y >= self.dim - self._player_rows()]
        return black_positions + red_positions

    def usable_positions(self):
        """Returns a generator for positions on the board that a piece can occupy."""
        return self._usable_positions

    def _player_rows(self):
        """Returns the number of rows a player controls at game start"""
        return (self.dim - self._neutral_rows) / 2

    def __iter__(self):
        """Allows iteration over the entire set of pieces as tuples (player, x, y)"""
        for player in [BLACK, RED]:
            for piece in self._player_pieces[player]:
                yield piece

    def __getitem__(self, loc):
        """Returns the piece occupying the position specified as a tuple (x,y)"""
        return self._loc_pieces[loc]

    def __contains__(self, loc):
        """Returns whether there is a piece at the specified location"""
        return loc in self._loc_pieces

    def __setitem__(self, loc, piece):
        """Sets the piece occupying the position specified by the tuple (x,y)
        to the specified player"""
        if piece.player not in players:
            raise CheckersException('Piece doe not belong to a player')
        if piece in self._player_pieces:
            self._player_pieces.pop(piece)
        if piece in self._loc_pieces.values():
            loc, piece = [item for item in self._loc_pieces.items() if item[0] == piece]
            self._loc_pieces.pop(loc)
        piece.board = self
        piece.location = loc
        self._loc_pieces[loc] = piece
        self._player_pieces[piece.player].add(piece)

    def winner(self):
        """Returns the player that has won the game or None if no winner."""
        num_black, num_red = len(self._player_pieces[BLACK]), len(self._player_pieces[RED])
        if num_black and not num_red:
            return BLACK
        elif num_red and not num_black:
            return RED
        else:
            return None

    def _valid_move(self, source, target):
        """Returns whether the move from source to target is a valid move."""
        # Not valid move if the source isn't occupied or target is occupied
        if not source in self or target in self:
            return False

        piece = self[source]
        player = piece.player

        if self.turn != player:
            return False

        moves = self._moves[player]

        if piece.king:
            moves = self._king_moves

        return (target in moves[source] and not self._possible_jump()) or self._valid_jump(source, target)

    def _valid_jump(self, source, target):
        """Returns whether the move from source to target is a valid jump."""
        move = (source, target)
        # Not valid move if the source isn't occupied or target is occupied
        if not source in self or target in self:
            return False

        piece = self[source]
        player = piece.player

        if self.turn != player:
            return False

        jumps = self._jumps[player]

        if piece.king:
            jumps = self._king_jumps

        if target in jumps[source] and move in self._captures:
            capture = self._captures[move]
            if capture in self and self[capture].player == opponent[player]:
                return True

        return False

    def _possible_jump_from(self, loc):
        """Returns whether the current player can jump from a given location."""
        # Consider the piece type and look at king jumps
        jump_targets = self._jumps[self.turn][loc]
        if self[loc].king:
            jump_targets = self._king_jumps[loc]
        for target in jump_targets:
            if self._valid_jump(loc, target):
                return True
        return False

    def _possible_jump(self):
        """Returns whether the current player has a possible jump."""
        for p in self._player_pieces[self.turn]:
            if self._possible_jump_from(p.location):
                return True
        return False

    def _perform_move(self, source, target):
        """Remove the captured piece and return location, or None if not a capture. Should have already validated as
        valid move with _valid_move before calling this."""
        result = None
        piece = self[source]
        player = piece.player
        moves, jumps = self._moves[player], self._jumps[player]
        if piece.king:
            moves, jumps = self._king_moves, self._king_jumps
        if target in jumps[source]:  # Handle a capture
            capture = self._captures[(source, target)]
            captured_piece = self[capture]
            self._player_pieces[captured_piece.player].remove(captured_piece)  # Remove piece from player
            self._loc_pieces.pop(capture)  # Remove captured piece from board
            captured_piece.location = None  # Captured piece will no longer have a location
            result = captured_piece
            self.last_jump_target = target
        else:
            self.last_jump_target = None
        # Move piece to target destination
        self._loc_pieces.pop(source, None)  # Remove piece from original location
        self._loc_pieces[target] = piece
        piece.location = target
        # King the piece if it moved into king row
        if not piece.king:
            if player == RED:
                piece.king = piece.location[1] == 0
            elif player == BLACK:
                piece.king = piece.location[1] == self.dim - 1
        # Update the turn if it changed
        if not self.last_jump_target or not self._possible_jump_from(self.last_jump_target):
            self.turn = opponent[self.turn]
        return result

    def move(self, source, target):
        """Moves the piece at source position to target and returns None or the location of a captured piece.
        It throws a InvalidMoveError if the move is not valid."""
        if not self._valid_move(source, target):
            raise InvalidMoveException("invalid move from %s to %s" % (source, target))
        return self._perform_move(source, target)

    def __str__(self):
        """Returns the board in string form."""
        result = ""
        for y in xrange(self.dim):
            for x in xrange(self.dim):
                loc = (x, y)
                if loc in self:
                    result += str(self[loc])
                else:
                    result += '*'
            result += '\n'
        return result
