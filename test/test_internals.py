from unittest import TestCase
from checkers.internals import Board, RED, BLACK


class Test_Checkers(TestCase):

    def setUp(self):
        self.state = Board()

    def test_no_winner(self):
        self.assertTrue(self.state.winner() is None, 'Initial board should have no winner')

    def test_black_wins(self):
        self.state._player_pieces[RED] = []
        self.assertEqual(BLACK, self.state.winner(), "Black should be winner")

    def test_red_wins(self):
        self.state._player_pieces[BLACK] = []
        self.assertEqual(RED, self.state.winner(), "Red should be winner")

    def test_getitem(self):
        self.assertEqual(self.state[(7, 0)], BLACK, "Top right corner should be black piece")

    def test_repr_start(self):
        expected = "*B*B*B*B\nB*B*B*B*\n*B*B*B*B\n********\n********\nR*R*R*R*\n*R*R*R*R\nR*R*R*R*\n"
        self.assertEqual(expected, self.state.__repr__(), "Board repr should match init game state")

    def test_set_item(self):
        self.state[(7, 0)] = RED
        self.assertEqual(self.state[(7, 0)], RED, "Top right corner should be red after setting")
