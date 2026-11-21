import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agents.alpha_beta.elagage import best_move
from agents.minimax.minimax import Minimax
from agents.random.random_agent import random_move
from awale.ai.qlearning import QLearningAgent, decode_action, encode_action, encode_state, _opponent_move
from engine.game import Game
from engine.random_agent.agent import RandomAgent
from tests.test_engine import position


class AuditRegressionTests(unittest.TestCase):
    def fresh(self, **kwargs):
        return QLearningAgent(load_models=False, **kwargs)

    def test_all_direct_agents_respect_score_repetition_and_limit(self):
        ended = [position([1]*12, (25,11)), Game(max_plies=1), Game()]
        ended[1].play_move(0)
        ended[2]._repeated = True
        for game in ended:
            self.assertIsNone(random_move(game))
            self.assertIsNone(RandomAgent(game.current_player).choose_move(game))
            self.assertIsNone(self.fresh().choose_move(game,True))

    def test_legacy_random_rejects_wrong_player(self):
        with self.assertRaises(ValueError):
            RandomAgent(2).choose_move(Game())
        for player in (0,3,True):
            with self.assertRaises(ValueError):
                RandomAgent(player)

    def test_minimax_rejects_inconsistent_active_player(self):
        game=Game()
        with self.assertRaises(ValueError):
            Minimax(2).choose_move(game.board,2,game=game)

    def test_immediate_win_wins_tie_against_delayed_forced_win(self):
        game=position([0,0,0,1,1,1,1,3,4,0,1,4],(9,23),2)
        self.assertEqual(best_move(game,3)[0],11)
        for _ in range(10):
            self.assertEqual(Minimax(3).choose_move(game.board,2,9,23,game=game)[0],11)

    def test_two_ply_trap_has_unique_safe_move(self):
        game=position([0,0,1,2,4,2,1,1,0,1,0,0],(22,14),2)
        self.assertEqual(best_move(game,2)[0],7)
        self.assertEqual(Minimax(2).choose_move(game.board,2,22,14,game=game)[0],7)

    def test_terminal_bellman_update_never_bootstraps(self):
        a=self.fresh(alpha=.25,gamma=.9)
        a.q_table={'s':{'2':10},'next':{'0':100000}}
        a.update('s',2,4,'next',[0],True)
        self.assertEqual(a._get_q('s',2),8.5)

    def test_nonterminal_bellman_update_matches_arithmetic(self):
        a=self.fresh(alpha=.2,gamma=.9)
        a.q_table={'s':{'2':5},'next':{'0':7,'1':3,'5':999}}
        a.update('s',2,-2,'next',[0,1],False)
        self.assertAlmostEqual(a._get_q('s',2),4.86)

    def test_hyperparameters_are_bounded_and_finite(self):
        for kwargs in ({'alpha':0},{'alpha':2},{'gamma':-1},{'gamma':float('nan')},
                       {'epsilon':2},{'epsilon_min':-.1},{'alpha':True},{'epsilon':.01,'epsilon_min':.05}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                self.fresh(**kwargs)

    def test_epsilon_decay_reaches_floor_and_stays_there(self):
        a=self.fresh(epsilon=1,epsilon_min=.05)
        a.set_epsilon_decay(100)
        values=[a.epsilon]
        for _ in range(120):
            a.decay_epsilon();values.append(a.epsilon)
        self.assertTrue(all(x>=y for x,y in zip(values,values[1:])))
        self.assertAlmostEqual(a.epsilon,.05)
        with self.assertRaises(ValueError):
            a.set_epsilon_decay(0)

    def test_state_rotation_and_relative_actions_are_consistent(self):
        game=Game();game.play_move(0);game.play_move(6)
        rotated=game.copy()
        rotated.board.holes=game.board.holes[6:]+game.board.holes[:6]
        rotated.score_p1,rotated.score_p2=game.score_p2,game.score_p1
        rotated.current_player=3-game.current_player
        self.assertEqual(encode_state(game),encode_state(rotated))
        for move in game.get_valid_moves():
            action=encode_action(game,move)
            self.assertEqual(decode_action(rotated,action),(move+6)%12)
        with self.assertRaises(ValueError):
            encode_action(game,6)
        with self.assertRaises(ValueError):
            decode_action(game,6)

    def test_checkpoint_roundtrip_preserves_all_training_parameters(self):
        with tempfile.TemporaryDirectory() as d:
            a=self.fresh(model_dir=d,alpha=.7,gamma=.4,epsilon=.6,epsilon_min=.1)
            a.set_epsilon_decay(100)
            a.q_table={'s':{'2':-3.5}}
            a.total_episodes=17
            a.save_latest()
            with patch('builtins.print'):
                b=QLearningAgent(model_dir=d,checkpoint='latest')
            self.assertEqual(a._checkpoint_payload(),b._checkpoint_payload())
            self.assertEqual(list(Path(d).glob('*.tmp')),[])

    def test_malformed_checkpoint_falls_back_without_partial_loading(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d,'q_table_best.json').write_text(json.dumps({'q_table':[],'epsilon':.01}),encoding='utf-8')
            Path(d,'q_table_latest.json').write_text(json.dumps({'q_table':{'s':{'2':1}},'total_episodes':5}),encoding='utf-8')
            with patch('builtins.print'):
                a=QLearningAgent(model_dir=d)
            self.assertEqual(a.total_episodes,5)
            self.assertEqual(a.q_table,{'s':{'2':1}})
            self.assertEqual(a.epsilon,1)

    def test_illegal_actions_and_malformed_agent_results_are_rejected(self):
        a=self.fresh()
        with self.assertRaises(ValueError):
            a.update('s',6,1,'',[],True)
        with self.assertRaises(ValueError):
            a.update('s',0,1,'',[],False)
        for value in ((),(0,),(0,1,2)):
            with self.assertRaises(ValueError):
                _opponent_move(Game(),lambda g:value)
