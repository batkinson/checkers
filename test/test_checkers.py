from checkers.checkers import screen_init
from unittest import TestCase


class TestScreen(TestCase):

    def setUp(self):
        self.screen = screen_init()

    def test_screen_something(self):
        self.assertEqual(self.screen.__class__.__name__, 'Surface')
