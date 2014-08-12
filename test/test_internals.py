from unittest import TestCase
from checkers.internals import Checkers, RED, BLACK


class Test_Checkers(TestCase):

    def setUp(self):
        self.state = Checkers()

    def test_no_winner(self):
        self.assert_(self.state.winner() is None, 'Initial board should have no winner')

    def test_black_wins(self):
        self.state.pieces[RED] = []
        self.assertEqual(BLACK, self.state.winner(), "Black should be winner")

    def test_red_wins(self):
        self.state.pieces[BLACK] = []
        self.assertEqual(RED, self.state.winner(), "Red should be winner")
