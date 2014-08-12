
RED = "red"
BLACK = "black"

class Checkers:

    def __init__(self, dim=8):
        """Create initial game state for normal checkers game."""
        self.dim = dim
        self._neutral_rows = 2
        self.pieces = {BLACK: [], RED: []}
        for player, x, y in self._start_positions():
            self.pieces[player].append((x, y))

    def _start_positions(self):
        """Returns a list of (player,x,y) tuples for start positions"""
        black_positions = [(BLACK, x, y) 
                    for y in range(0, self._player_rows()) 
                    for x in range((y + 1) % 2, self.dim, 2)]
        red_positions = [(RED, x, y) 
                    for y in range(self.dim - self._player_rows(), self.dim) 
                    for x in range((y + 1) % 2, self.dim, 2)]
        return black_positions + red_positions

    def _player_rows(self):
        """Returns the number of rows a player controls at game start"""
        return (self.dim - self._neutral_rows) / 2

    def __iter__(self):
        """Allows iteration over the entire set of pieces as tuples (player, x, y)"""
        for player in [BLACK, RED]:
            for piece in self.pieces[player]:
                yield (player, piece[0], piece[1])

    def __getitem__(self, xy):
        """Returns the piece occupying the position specified as a tuple (x,y)"""
        for player in [BLACK, RED]:
            x,y = xy
            if (x, y) in self.pieces[player]:
                return player

    def __setitem__(self, xy, player):
        """Sets the piece occupying the position specified by the tuple (x,y)
        to the specified player"""
        x,y = xy
        existing = self[xy]
        if existing != player:
            self.pieces[existing].remove((x, y))
        self.pieces[player].append((x, y))

    def winner(self):
        """Returns the player that has won the game or None if no winner."""
        num_black, num_red = len(self.pieces[BLACK]), len(self.pieces[RED])
        if (num_black and not num_red):
            return BLACK
        elif (num_red and not num_black):
            return RED

    def __repr__(self):
        """Returns the board representation."""
        result = ""
        for y in range(self.dim):
            for x in range(self.dim):
                if self[(x, y)] == BLACK:
                    result += 'B'
                elif self[(x,y)] == RED:
                    result += 'R'
                else:
                    result += '*'
            result += '\n'
        return result
