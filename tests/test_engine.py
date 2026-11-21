import random
import unittest

from engine.board import Board
from engine.game import Game
from engine.rules import Rules


def position(holes, scores=(0, 0), player=1, **kwargs):
    game = Game(**kwargs)
    game.board.holes = holes[:]
    game.score_p1, game.score_p2 = scores
    game.current_player = player
    return game


class EngineTests(unittest.TestCase):
    def test_capture_cannot_starve_when_an_alternative_exists(self):
        for offset, player in ((0, 1), (6, 2)):
            holes = [0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0]
            holes = holes[-offset:] + holes[:-offset] if offset else holes
            game = position(holes, player=player)
            self.assertEqual(Rules.get_valid_moves(game.board, player), [4 + offset])
            self.assertFalse(game.play_move(5 + offset))
            self.assertEqual(game.board.holes, holes)

    def test_unavoidable_starvation_is_allowed_by_project_variant(self):
        game = position([0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0], (23, 23))
        self.assertEqual(game.get_valid_moves(), [5])
        self.assertTrue(game.play_move(5))
        self.assertEqual(game.get_winner(), 1)

    def test_feeding_empty_opponent_is_mandatory(self):
        game = position([1, 0, 0, 0, 0, 1] + [0] * 6)
        self.assertEqual(Rules.get_valid_moves(game.board, 1), [5])

    def test_kroo_skips_start_on_multiple_laps(self):
        board = Board()
        board.holes = [23] + [0] * 11
        self.assertEqual(Rules.sow(board, 0), 1)
        self.assertEqual(board.holes, [0, 3] + [2] * 10)

    def test_backwards_capture_stops_at_non_capture_hole(self):
        board = Board()
        board.holes = [0] * 6 + [2, 4, 3, 2, 0, 0]
        self.assertEqual(Rules.capture(board, 9, 1), 5)
        self.assertEqual(board.holes[6:10], [2, 4, 0, 0])

    def test_bad_move_types_do_not_mutate_state(self):
        game = Game()
        before = game.position_key()
        for move in (None, (0, 1), '0', True, 0.0, -1, 12):
            self.assertFalse(game.play_move(move))
        self.assertEqual(game.position_key(), before)
        self.assertEqual(game.plies, 0)

    def test_score_end_refuses_further_play(self):
        game = position([1] * 12, (25, 11))
        self.assertFalse(game.play_move(0))
        self.assertEqual(game.get_valid_moves(), [])
        self.assertEqual(game.get_winner(), 1)
        self.assertEqual(game.get_children(), [])

    def test_blockade_final_scores_are_idempotent(self):
        game = position([0] * 6 + [1, 0, 0, 0, 0, 0], (24, 23))
        before = game.position_key()
        for _ in range(3):
            self.assertEqual(game.final_scores(), (24, 24))
            self.assertIsNone(game.get_winner())
        self.assertEqual(game.position_key(), before)

    def test_ongoing_game_has_no_winner(self):
        self.assertIsNone(position([1] * 12, (20, 16)).get_winner())

    def test_limit_is_a_draw_even_with_score_lead(self):
        game = position([1] * 12, (20, 16), max_plies=1)
        self.assertTrue(game.play_move(0))
        self.assertEqual(game.end_reason(), 'limite')
        self.assertIsNone(game.get_winner())

    def test_repeated_position_is_a_draw(self):
        game = position([1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0], (23, 23))
        while not game.is_game_over():
            self.assertTrue(game.play_move(game.get_valid_moves()[0]))
        self.assertEqual(game.end_reason(), 'repetition')
        self.assertIsNone(game.get_winner())

    def test_seed_conservation_and_copy_isolation_in_random_games(self):
        rng = random.Random(17)
        for _ in range(15):
            game = Game()
            while not game.is_game_over():
                copy = game.copy()
                move = rng.choice(game.get_valid_moves())
                self.assertTrue(game.play_move(move))
                self.assertEqual(sum(game.board.holes) + game.score_p1 + game.score_p2, 48)
                self.assertEqual(copy.plies, game.plies - 1)
                self.assertIsNot(copy._history, game._history)
