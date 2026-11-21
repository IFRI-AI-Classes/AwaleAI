import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from api import server
from tests.test_engine import position


class APITests(unittest.TestCase):
    def setUp(self):
        server._sessions.clear()
        self.client = TestClient(server.app)

    def start(self, ai=False):
        r = self.client.post('/api/game/start', json={
            'player1': {'name': 'A', 'type': 'ai' if ai else 'human'},
            'player2': {'name': 'B', 'type': 'human'},
        })
        self.assertEqual(r.status_code, 200)
        return r.json()

    def move(self, state, **overrides):
        payload = {'game_id': state['game_id'], 'version': state['version'],
                   'player': state['current_player'], 'pit_index': state['valid_moves'][0]}
        payload.update(overrides)
        return self.client.post('/api/game/move', json=payload)

    def ai_move(self, state, **overrides):
        payload = {'game_id': state['game_id'], 'version': state['version'],
                   'player': state['current_player'], 'agent': 'minimax', 'board': state['board']}
        payload.update(overrides)
        return self.client.post('/api/game/ai-move', json=payload)

    def test_games_are_isolated(self):
        first, second = self.start(), self.start()
        self.assertNotEqual(first['game_id'], second['game_id'])
        self.assertEqual(self.move(first).status_code, 200)
        snapshot = self.client.get('/api/game/' + second['game_id']).json()
        self.assertEqual(snapshot, second)

    def test_ai_rejects_wrong_player_and_wrong_type(self):
        state = self.start(ai=True)
        self.assertEqual(self.ai_move(state, player='player2').status_code, 400)
        self.assertEqual(self.move(state).status_code, 400)
        state = self.start()
        self.assertEqual(self.ai_move(state).status_code, 400)

    def test_human_rejects_wrong_player_without_mutation(self):
        state = self.start()
        self.assertEqual(self.move(state, player='player2').status_code, 400)
        self.assertEqual(self.client.get('/api/game/' + state['game_id']).json(), state)

    def test_concurrent_duplicate_moves_apply_once(self):
        state = self.start()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: self.move(state), range(2)))
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])
        self.assertEqual(self.client.get('/api/game/' + state['game_id']).json()['version'], 1)

    def test_stale_version_is_rejected(self):
        state = self.start()
        next_state = self.move(state).json()
        self.assertEqual(self.move(next_state, version=0).status_code, 409)

    def test_ai_snapshot_and_depth_are_validated(self):
        state = self.start(ai=True)
        self.assertEqual(self.ai_move(state, board=[0] * 12).status_code, 409)
        for depth in (0, -1, 9):
            self.assertEqual(self.ai_move(state, depth=depth).status_code, 400)
        for depth in (True, '2', 1.5):
            self.assertEqual(self.ai_move(state, depth=depth).status_code, 422)
        self.assertEqual(self.ai_move(state, board=[4] * 11).status_code, 422)

    def test_default_depth_telemetry_and_state_version(self):
        state = self.start(ai=True)
        response = self.ai_move(state)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['telemetry']['depth'], 2)
        self.assertGreater(data['telemetry']['nodes_explored'], 0)
        self.assertEqual(data['game_state']['version'], 1)
        self.assertEqual(data['game_state']['game_id'], state['game_id'])

    def test_invalid_agent_move_is_not_reported_as_success(self):
        state = self.start(ai=True)
        with patch('api.server.difficulty.choose_move_by_agent', return_value=(99, 1)):
            self.assertEqual(self.ai_move(state).status_code, 500)
        self.assertEqual(self.client.get('/api/game/' + state['game_id']).json(), state)

    def test_unknown_or_missing_game_id(self):
        state = self.start()
        self.assertEqual(self.move(state, game_id=str(uuid4())).status_code, 404)
        self.assertEqual(self.client.post('/api/game/move', json={'pit_index': 0, 'player': 'player1'}).status_code, 422)

    def test_game_ending_serialization_uses_engine_scores(self):
        state = self.start()
        session = server._sessions[state['game_id']]
        session.game = position([0] * 6 + [1, 0, 0, 0, 0, 0], (24, 23))
        snapshot = self.client.get('/api/game/' + state['game_id']).json()
        self.assertEqual(snapshot['scores'], {'player1': 24, 'player2': 24})
        self.assertEqual(snapshot['valid_moves'], [])
        self.assertTrue(snapshot['game_over'])
        self.assertIsNone(snapshot['winner'])

    def test_sessions_expire_and_capacity_is_bounded(self):
        with patch('api.server.MAX_SESSIONS', 1):
            state = self.start()
            r = self.client.post('/api/game/start', json={'player1': {}, 'player2': {}})
            self.assertEqual(r.status_code, 503)
            server._sessions[state['game_id']].last_used -= server.SESSION_TTL + 1
            self.assertEqual(self.client.get('/api/game/' + state['game_id']).status_code, 404)
            self.start()
