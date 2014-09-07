from unittest import TestCase
from checkers.internals import Board, Piece, RED, BLACK


class TestCheckers(TestCase):

    def setUp(self):
        self.state = Board()
        for player, x, y in self.state.start_positions():
            self.state.add_piece(Piece(player), (x, y))

    def test_no_winner(self):
        self.assertTrue(self.state.winner() is None, 'Initial board should have no winner')

    def test_black_wins(self):
        self.state._player_pieces[RED] = []
        self.assertEqual(BLACK, self.state.winner(), "Black should be winner")

    def test_red_wins(self):
        self.state._player_pieces[BLACK] = []
        self.assertEqual(RED, self.state.winner(), "Red should be winner")

    def test_getitem(self):
        self.assertEquals(self.state[(7, 0)].player, BLACK, "Top right corner should be black piece")

    def test_str(self):
        expected = "*b*b*b*b\nb*b*b*b*\n*b*b*b*b\n********\n********\nr*r*r*r*\n*r*r*r*r\nr*r*r*r*"
        self.assertEqual(expected, str(self.state), "Board str should match init game state")

    def test_set_item(self):
        p = Piece(RED)
        self.state[(7, 0)] = p
        self.assertEqual(self.state[(7, 0)], p, "Top right corner should be red after setting")

    def test_from_str(self):
        expected = "*b*b*b*b\nb*b*b*b*\n*b*B*b*b\n********\n********\nr*r*R*r*\n*r*r*r*r\nr*r*r*r*"
        self.assertEqual(expected, str(Board.from_str(expected)))
