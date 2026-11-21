import math
import json
import tempfile
from pathlib import Path
import random
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch, Mock

from agents.alpha_beta.elagage import alpha_beta, best_move
from agents.difficulty import choose_move_by_agent
from agents.heuristic.heuristic import WIN_SCORE, heuristic
from agents.minimax.minimax import Minimax
from awale.ai.qlearning import QLearningAgent, encode_state, run_episode, run_selfplay_episode, evaluate_agent
from engine.game import Game
from tests.test_engine import position


class SearchTests(unittest.TestCase):
    def test_immediate_victory_is_preferred_by_both_agents(self):
        game = position([1, 0, 1, 0, 0, 0, 1, 2, 0, 0, 1, 1], (18, 23), 2)
        for agent in ('minimax', 'alphabeta'):
            for depth in (1, 2, 3):
                self.assertEqual(choose_move_by_agent(game, agent, depth)[0], 11)

    def test_terminal_values_include_residual_seeds_and_draws(self):
        game = position([0] * 6 + [2] * 6, (22, 14))
        self.assertEqual(heuristic.evaluate(game, 1), -WIN_SCORE)
        self.assertEqual(heuristic.evaluate(game, 2), WIN_SCORE)
        game = position([1] * 12, (20, 16), max_plies=1)
        game.play_move(0)
        self.assertEqual(heuristic.evaluate(game, 1), 0)

    def test_finished_game_has_no_move_and_one_search_node(self):
        game = position([1] * 12, (25, 11))
        self.assertEqual(best_move(game, 3), (None, 1))
        mm = Minimax(3)
        self.assertEqual(mm.choose_move(game.board, 1, 25, 11, game=game), (None, 1))

    def test_alpha_beta_matches_exact_minimax_values_on_both_sides(self):
        rng = random.Random(19)
        for _ in range(20):
            game = Game()
            for _ in range(rng.randint(1, 70)):
                if game.is_game_over():
                    break
                game.play_move(rng.choice(game.get_valid_moves()))
            if game.is_game_over():
                continue
            before = game.position_key()
            for depth in (1, 2, 3):
                mm = Minimax(depth)
                value, _ = mm.minimax(game, depth, game.current_player)
                self.assertEqual(alpha_beta(game, depth, -math.inf, math.inf, game.current_player), value)
                move, nodes = best_move(game, depth)
                child = game.copy()
                child.play_move(move)
                chosen, _ = mm.minimax(child, depth - 1, game.current_player)
                self.assertEqual(chosen, value)
                self.assertLessEqual(nodes, mm._nodes)
            self.assertEqual(game.position_key(), before)

    def test_real_game_limit_is_preserved_in_search(self):
        game = Game(max_plies=1)
        self.assertEqual(alpha_beta(game, 3, -math.inf, math.inf, 1), 0)
        self.assertEqual(Minimax(3).minimax(game, 3, 1)[0], 0)

    def test_parallel_searches_have_independent_node_counts(self):
        game = Game()
        expected = best_move(game, 3)
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(list(pool.map(lambda _: best_move(game, 3), range(8))), [expected] * 8)

    def test_depth_bounds_are_enforced(self):
        for agent, invalid in (('minimax', 9), ('alphabeta', 13)):
            for depth in (0, -1, True, 1.5, invalid):
                with self.assertRaises(ValueError):
                    choose_move_by_agent(Game(), agent, depth)


class QLearningTests(unittest.TestCase):
    def agent(self):
        with patch.object(QLearningAgent, 'load'):
            return QLearningAgent(epsilon=0, epsilon_min=0)

    def test_tuple_opponent_actually_plays_and_agent_gets_turns(self):
        for player in (1, 2):
            agent = self.agent()
            agent.choose_move = Mock(wraps=agent.choose_move)
            run_episode(agent, lambda g: best_move(g, 1), player, False)
            self.assertGreater(agent.choose_move.call_count, 1)
            self.assertEqual(agent.q_table, {})

    def test_training_bootstraps_after_the_actual_opponent_reply(self):
        agent = self.agent()
        agent.update = Mock(wraps=agent.update)
        run_episode(agent, lambda g: best_move(g, 1), 1)
        calls = agent.update.call_args_list
        self.assertTrue(calls[-1].args[-1])
        for current, following in zip(calls, calls[1:]):
            self.assertEqual(current.args[3], following.args[0])
            self.assertTrue(current.args[4])

    def test_bellman_update_uses_best_legal_action(self):
        agent = self.agent()
        agent.alpha, agent.gamma = 1, .5
        agent.q_table = {'next': {'0': 4, '1': 9, '5': 999}}
        agent.update('current', 2, 3, 'next', [0, 1], False)
        self.assertEqual(agent._get_q('current', 2), 7.5)

    def test_invalid_opponent_is_reported(self):
        with self.assertRaises(ValueError):
            run_episode(self.agent(), lambda g: (99, 4), 2, False)

    def test_selfplay_finishes_both_players_transitions(self):
        agent = self.agent()
        agent.update = Mock(wraps=agent.update)
        run_selfplay_episode(agent)
        self.assertEqual(sum(call.args[-1] for call in agent.update.call_args_list), 2)
        for call in agent.update.call_args_list:
            if not call.args[-1]:
                self.assertTrue(call.args[3])
                self.assertTrue(call.args[4])

    def test_evaluation_runs_exact_requested_count(self):
        with patch('awale.ai.qlearning.run_episode', return_value=(None, 0)) as run:
            self.assertEqual(evaluate_agent(self.agent(), 100), 0)
            self.assertEqual(run.call_count, 100)
        with self.assertRaises(ValueError):
            evaluate_agent(self.agent(), 0)

    def test_play_prefers_best_but_training_resumes_latest(self):
        with tempfile.TemporaryDirectory() as directory:
            best, latest = Path(directory) / 'best.json', Path(directory) / 'latest.json'
            best.write_text(json.dumps({'q_table': {'best': {'0': 1}}, 'total_episodes': 10}), encoding='utf-8')
            latest.write_text(json.dumps({'q_table': {'latest': {'0': 2}}, 'total_episodes': 20}), encoding='utf-8')
            with patch('awale.ai.qlearning.PATH_BEST', str(best)), patch('awale.ai.qlearning.PATH_LATEST', str(latest)), patch('builtins.print'):
                player = QLearningAgent()
                training = QLearningAgent(checkpoint='latest')
            self.assertEqual(player.total_episodes, 10)
            self.assertEqual(training.total_episodes, 20)
            self.assertEqual(training.loaded_path, str(latest))
