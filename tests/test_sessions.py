"""Persistence, failure and concurrency regressions using isolated SQLite files."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, contextmanager
import json
import os
import random
from pathlib import Path
import sqlite3
import socket
import subprocess
import sys
import tempfile
import time
from threading import Barrier, Event
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
import httpx

from api import server
from api.session_store import SQLiteSessionStore, StorageError, VersionConflict, _encode
from engine.game import Game


class SessionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'awale.sqlite3'
        self.app = server.create_app(self.path)
        self.store = self.app.state.session_store
        self.client = TestClient(self.app)

    def start(self, ai=False, client=None, players=None):
        response = (client or self.client).post('/api/game/start', json=players or {
            'player1': {'name': 'Élodie', 'type': 'ai' if ai else 'human'},
            'player2': {'name': 'Joueur 2', 'type': 'human'},
        })
        self.assertEqual(response.status_code, 200)
        return response.json()

    def move(self, state, client=None, pit_index=None):
        return (client or self.client).post('/api/game/move', json={
            'game_id': state['game_id'], 'version': state['version'],
            'player': state['current_player'],
            'pit_index': state['valid_moves'][0] if pit_index is None else pit_index,
        })

    def ai_move(self, state, agent):
        return self.client.post('/api/game/ai-move', json={
            'game_id': state['game_id'], 'version': state['version'],
            'player': state['current_player'], 'agent': agent, 'depth': 2,
            'board': state['board'],
        })

    def row(self, game_id):
        with self.connection() as connection:
            connection.row_factory = sqlite3.Row
            return dict(connection.execute('SELECT * FROM sessions WHERE game_id = ?',
                                           (game_id,)).fetchone())

    @contextmanager
    def connection(self):
        with closing(sqlite3.connect(self.path)) as connection:
            with connection:
                yield connection

    def fixture(self, game):
        key = str(uuid4())
        game._history = {game.position_key()}
        self.store.create(key, game, {
            'player1': {'name': 'A', 'type': 'human'},
            'player2': {'name': 'B', 'type': 'human'},
        }, server.SESSION_TTL, server.MAX_SESSIONS)
        return self.client.get('/api/game/' + key).json()

    def test_creation_and_every_human_move_are_persisted(self):
        state = self.start()
        for version in range(5):
            row = self.row(state['game_id'])
            payload = json.loads(row['state'])
            self.assertEqual(row['version'], version)
            self.assertEqual(payload['game']['plies'], version)
            self.assertEqual(payload['game']['holes'], state['board'])
            self.assertEqual(payload['players']['player1']['name'], 'Élodie')
            response = self.move(state)
            self.assertEqual(response.status_code, 200)
            state = response.json()
        self.assertEqual(self.row(state['game_id'])['version'], 5)

    def test_each_ai_agent_saves_its_legal_move(self):
        for agent in ('random', 'minimax', 'alphabeta', 'qlearning'):
            with self.subTest(agent=agent):
                state = self.start(ai=True)
                response = self.ai_move(state, agent)
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertIn(data['telemetry']['pit_played'], state['valid_moves'])
                restarted = TestClient(server.create_app(self.path))
                self.assertEqual(restarted.get('/api/game/' + state['game_id']).json(), data['game_state'])
                self.assertEqual(self.row(state['game_id'])['version'], 1)

    def test_full_state_and_runtime_locks_are_restored(self):
        state = self.start()
        state = self.move(state).json()
        before = self.store.load(state['game_id'])
        restarted = SQLiteSessionStore(self.path)
        after = restarted.load(state['game_id'])
        self.assertEqual(_encode(after), _encode(before))
        self.assertEqual(after.expires_at, before.expires_at)
        self.assertIsNot(after.lock, before.lock)
        self.assertTrue(after.lock.acquire(blocking=False))
        after.lock.release()
        self.assertNotIn('lock', json.loads(self.row(state['game_id'])['state']))
        self.assertIs(after.lock, restarted.lock_for(state['game_id']))

    def test_game_continues_in_a_new_process(self):
        code = """
import json, sys
from fastapi.testclient import TestClient
from api.server import app
client = TestClient(app)
if len(sys.argv) == 1:
    state = client.post('/api/game/start', json={'player1':{}, 'player2':{}}).json()
else:
    response = client.get('/api/game/' + sys.argv[1])
    assert response.status_code == 200
    state = response.json()
response = client.post('/api/game/move', json={
    'game_id':state['game_id'], 'version':state['version'],
    'player':state['current_player'], 'pit_index':state['valid_moves'][0]})
assert response.status_code == 200
print(json.dumps(response.json()))
"""
        environment = dict(os.environ, AWALE_DB_PATH=str(self.path))
        def run(*args):
            process = subprocess.run(
                [sys.executable, '-B', '-X', 'utf8', '-c', code, *args],
                cwd=Path(__file__).resolve().parents[1], env=environment,
                capture_output=True, text=True, encoding='utf-8', check=True, timeout=20,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
            return json.loads(process.stdout)
        first = run()
        second = run(first['game_id'])
        self.assertEqual(first['version'], 1)
        self.assertEqual(second['version'], 2)
        self.assertEqual(second['game_id'], first['game_id'])
        self.assertEqual(self.client.get('/api/game/' + first['game_id']).json(), second)

    def test_repetition_history_survives_restart_before_the_draw(self):
        game = Game()
        game.board.holes = [1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0]
        game.score_p1 = game.score_p2 = 23
        state = self.fixture(game)
        expected = game.copy()
        expected._history = {expected.position_key()}
        while not expected.is_game_over():
            expected.play_move(expected.get_valid_moves()[0])
        self.assertEqual(expected.end_reason(), 'repetition')
        for step in range(expected.plies):
            if step == expected.plies // 2:
                self.app = server.create_app(self.path)
                self.client = TestClient(self.app)
            response = self.move(state)
            self.assertEqual(response.status_code, 200)
            state = response.json()
        restored = SQLiteSessionStore(self.path).load(state['game_id']).game
        self.assertEqual(restored._history, expected._history)
        self.assertTrue(restored._repeated)
        self.assertEqual(state['end_reason'], 'repetition')
        self.assertTrue(state['game_over'])
        self.assertIsNone(state['winner'])
        self.assertEqual(self.move(dict(state, valid_moves=[0])).status_code, 400)

    def test_limit_and_winning_capture_are_restored(self):
        games = [Game(max_plies=1), Game()]
        games[1].board.holes = [0, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0, 0]
        games[1].score_p1 = games[1].score_p2 = 23
        for game, reason in zip(games, ('limite', 'score')):
            with self.subTest(reason=reason):
                state = self.fixture(game)
                response = self.move(state)
                self.assertEqual(response.status_code, 200)
                result = response.json()
                restored = SQLiteSessionStore(self.path).load(state['game_id']).game
                self.assertEqual(restored.end_reason(), reason)
                self.assertEqual(restored.max_plies, game.max_plies)
                self.assertEqual(server._game_to_state(restored, state['game_id']), result)
                self.assertEqual(sum(restored.board.holes) + restored.score_p1 + restored.score_p2, 48)

    def test_blockade_preserves_raw_scores_and_remaining_seeds(self):
        game = Game()
        game.board.holes = [0] * 6 + [1, 0, 0, 0, 0, 0]
        game.score_p1, game.score_p2 = 24, 23
        state = self.fixture(game)
        restored = SQLiteSessionStore(self.path).load(state['game_id']).game
        self.assertEqual((restored.score_p1, restored.score_p2), (24, 23))
        self.assertEqual(restored.final_scores(), (24, 24))
        self.assertEqual(state['scores'], {'player1': 24, 'player2': 24})
        self.assertEqual(restored.board.holes, game.board.holes)

    def test_expiration_is_utc_persistent_and_renewed_on_access(self):
        now = 1_900_000_000
        with patch('api.session_store.time.time', return_value=now):
            state = self.start()
        self.assertEqual(self.row(state['game_id'])['expires_at'], now + server.SESSION_TTL)
        restarted = TestClient(server.create_app(self.path))
        with patch('api.session_store.time.time', return_value=now + server.SESSION_TTL - 1):
            self.assertEqual(restarted.get('/api/game/' + state['game_id']).status_code, 200)
        renewed = now + 2 * server.SESSION_TTL - 1
        self.assertEqual(self.row(state['game_id'])['expires_at'], renewed)
        with patch('api.session_store.time.time', return_value=renewed):
            self.assertEqual(restarted.get('/api/game/' + state['game_id']).status_code, 404)

    def test_concurrent_moves_across_two_applications_commit_once(self):
        state = self.start()
        second = TestClient(server.create_app(self.path))
        barrier = Barrier(2)
        check = server._check_turn
        def simultaneous_check(*args):
            check(*args)
            barrier.wait(timeout=5)
        with patch('api.server._check_turn', side_effect=simultaneous_check):
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(lambda client: self.move(state, client), [self.client, second]))
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])
        self.assertEqual(self.row(state['game_id'])['version'], 1)
        self.assertEqual(self.move(state, second).status_code, 409)

    def test_concurrent_ai_moves_across_two_applications_commit_once(self):
        state = self.start(ai=True)
        second = TestClient(server.create_app(self.path))
        barrier = Barrier(2)
        def choose(game, agent, depth):
            barrier.wait(timeout=5)
            return game.get_valid_moves()[0], None
        payload = {'game_id': state['game_id'], 'version': 0, 'player': 'player1', 'agent': 'random'}
        with patch('api.server.difficulty.choose_move_by_agent', side_effect=choose):
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(lambda client: client.post('/api/game/ai-move', json=payload),
                                          [self.client, second]))
        self.assertEqual(sorted(r.status_code for r in responses), [200, 409])
        self.assertEqual(self.row(state['game_id'])['version'], 1)

    def test_ai_search_does_not_hold_the_database_write_lock(self):
        state = self.start(ai=True)
        started, release = Event(), Event()
        def choose(game, agent, depth):
            started.set()
            if not release.wait(timeout=10):
                raise AssertionError('AI search was not released')
            return game.get_valid_moves()[0], None
        with patch('api.server.difficulty.choose_move_by_agent', side_effect=choose):
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(self.ai_move, state, 'random')
                try:
                    self.assertTrue(started.wait(timeout=5))
                    other = self.start()
                    self.assertEqual(self.move(other).status_code, 200)
                finally:
                    release.set()
                self.assertEqual(future.result(timeout=5).status_code, 200)

    def test_failed_writes_roll_back_creation_human_and_ai_moves(self):
        human, ai = self.start(), self.start(ai=True)
        write = self.store._write_session
        def fail_after_write(*args, **kwargs):
            write(*args, **kwargs)
            raise sqlite3.OperationalError('simulated disk failure after SQL write')
        with patch.object(self.store, '_write_session', side_effect=fail_after_write):
            with self.assertLogs('api.server', level='ERROR'):
                creation = self.client.post('/api/game/start', json={'player1': {}, 'player2': {}})
                human_move = self.move(human)
                ai_move = self.ai_move(ai, 'random')
        for response in (creation, human_move, ai_move):
            self.assertEqual(response.status_code, 503)
            self.assertNotIn('game_state', response.json())
            self.assertNotIn('telemetry', response.json())
        with self.connection() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 2)
        for state in (human, ai):
            self.assertEqual(self.row(state['game_id'])['version'], 0)
            self.assertEqual(self.client.get('/api/game/' + state['game_id']).json(), state)
        self.assertEqual(self.move(human).status_code, 200)
        self.assertEqual(self.ai_move(ai, 'random').status_code, 200)

    def test_failure_at_commit_does_not_report_a_successful_move(self):
        state = self.start()
        connect, write = self.store._connect, self.store._write_session
        def foreign_keys_enabled():
            connection = connect()
            connection.execute('PRAGMA foreign_keys = ON')
            return connection
        def invalid_deferred_constraint(connection, *args, **kwargs):
            write(connection, *args, **kwargs)
            connection.execute('CREATE TABLE commit_parent(id INTEGER PRIMARY KEY)')
            connection.execute('CREATE TABLE commit_child(parent_id INTEGER REFERENCES commit_parent(id) '
                               'DEFERRABLE INITIALLY DEFERRED)')
            connection.execute('INSERT INTO commit_child VALUES (99)')
        with patch.object(self.store, '_connect', side_effect=foreign_keys_enabled):
            with patch.object(self.store, '_write_session', side_effect=invalid_deferred_constraint):
                with self.assertLogs('api.server', level='ERROR'):
                    response = self.move(state)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.client.get('/api/game/' + state['game_id']).json(), state)

    def test_unavailable_sqlite_returns_503_for_health_creation_and_moves(self):
        human, ai = self.start(), self.start(ai=True)
        with patch('api.session_store.sqlite3.connect', side_effect=sqlite3.OperationalError('unavailable')):
            with self.assertLogs('api.server', level='ERROR'):
                responses = [
                    self.client.get('/'),
                    self.client.post('/api/game/start', json={'player1': {}, 'player2': {}}),
                    self.client.get('/api/game/' + human['game_id']),
                    self.move(human), self.ai_move(ai, 'random'),
                ]
        self.assertEqual([r.status_code for r in responses], [503] * len(responses))
        self.assertEqual(self.move(human).status_code, 200)

    def test_invalid_database_path_and_locked_database_return_503(self):
        invalid = TestClient(server.create_app(self.path.parent))
        with self.assertLogs('api.server', level='ERROR'):
            self.assertEqual(invalid.get('/').status_code, 503)
        state = self.start()
        self.store.timeout = 0.02
        with self.connection() as blocking:
            blocking.execute('BEGIN IMMEDIATE')
            with self.assertLogs('api.server', level='ERROR'):
                self.assertEqual(self.move(state).status_code, 503)
        self.assertEqual(self.move(state).status_code, 200)

    def test_corrupt_or_unsupported_snapshot_is_not_silently_reset(self):
        state = self.start()
        original = self.row(state['game_id'])['state']
        for value in ('{broken', json.dumps({'schema_version': 999}),
                      json.dumps({'schema_version': 1, 'players': {}})):
            with self.subTest(value=value):
                with self.connection() as connection:
                    connection.execute('UPDATE sessions SET state = ? WHERE game_id = ?', (value, state['game_id']))
                with self.assertLogs('api.server', level='ERROR'):
                    self.assertEqual(self.move(state).status_code, 503)
                self.assertEqual(self.row(state['game_id'])['state'], value)
        with self.connection() as connection:
            connection.execute('UPDATE sessions SET state = ? WHERE game_id = ?', (original, state['game_id']))
        self.assertEqual(self.move(state).status_code, 200)

    def test_incompatible_database_schema_returns_503_without_recreating_it(self):
        with self.connection() as connection:
            connection.execute('CREATE TABLE sessions(game_id TEXT PRIMARY KEY)')
            connection.execute('INSERT INTO sessions VALUES (?)', ('existing-game',))
        with self.assertLogs('api.server', level='ERROR'):
            self.assertEqual(self.client.get('/').status_code, 503)
            self.assertEqual(self.client.post('/api/game/start', json={'player1': {}, 'player2': {}}).status_code, 503)
        with self.connection() as connection:
            self.assertEqual(connection.execute('SELECT game_id FROM sessions').fetchall(), [('existing-game',)])

    def advance(self, state, client, rng, steps):
        expected = self.store.load(state['game_id']).game.copy()
        for _ in range(steps):
            if expected.is_game_over():
                break
            hole = rng.choice(expected.get_valid_moves())
            self.assertTrue(expected.play_move(hole))
            response = self.move(state, client, pit_index=hole)
            self.assertEqual(response.status_code, 200)
            state = response.json()
            self.assertEqual(state, server._game_to_state(expected, state['game_id']))
        return state

    def test_two_http_clients_keep_boards_scores_players_and_histories_independent(self):
        other = TestClient(self.app)
        self.client.cookies.set('session', 'client-a')
        other.cookies.set('session', 'client-b')
        first = self.start(players={'player1': {'name': 'Alice'}, 'player2': {'name': 'André'}})
        second = self.start(client=other, players={'player1': {'name': 'Béatrice'}, 'player2': {'name': 'Benoît'}})
        rngs = [random.Random(4), random.Random(17)]
        for _ in range(5):
            before_b = _encode(self.store.load(second['game_id']))
            first = self.advance(first, self.client, rngs[0], 3)
            self.assertEqual(_encode(self.store.load(second['game_id'])), before_b)
            before_a = _encode(self.store.load(first['game_id']))
            second = self.advance(second, other, rngs[1], 2)
            self.assertEqual(_encode(self.store.load(first['game_id'])), before_a)
        self.assertNotEqual(first['board'], second['board'])
        self.assertNotEqual(first['current_player'], second['current_player'])
        self.assertEqual(self.store.load(first['game_id']).players['player1']['name'], 'Alice')
        self.assertEqual(self.store.load(second['game_id']).players['player1']['name'], 'Béatrice')
        for state in (first, second):
            saved = self.store.load(state['game_id'])
            self.assertEqual(saved.game_id, state['game_id'])
            self.assertEqual(len(saved.moves), state['version'])
            self.assertEqual([m['version'] for m in saved.moves], list(range(1, state['version'] + 1)))
            for client in (self.client, other):
                response = client.get('/api/game/' + state['game_id'])
                self.assertEqual(response.json(), state)
                self.assertEqual(response.headers['cache-control'], 'no-store')
                self.assertNotIn('set-cookie', response.headers)

    def test_real_captures_change_only_the_target_game_in_both_directions(self):
        other = TestClient(self.app)
        states = [self.start(), self.start(client=other)]
        for index, client in enumerate((self.client, other)):
            unchanged = states[1 - index]
            rng = random.Random(42 + index)
            for _ in range(200):
                state = states[index]
                self.assertFalse(state['game_over'], 'Expected a capture before the game ends')
                response = self.move(state, client, rng.choice(state['valid_moves']))
                self.assertEqual(response.status_code, 200)
                states[index] = response.json()
                self.assertEqual(self.client.get('/api/game/' + unchanged['game_id']).json(), unchanged)
                if sum(states[index]['scores'].values()) > sum(state['scores'].values()):
                    break
            else:
                self.fail('No capture was observed')
            self.assertGreater(sum(states[index]['scores'].values()), 0)

    def test_one_hundred_games_play_in_parallel_against_independent_engine_states(self):
        clients = [TestClient(server.create_app(self.path)) for _ in range(4)]
        def play(index):
            client = clients[index % len(clients)]
            state = self.start(client=client, players={
                'player1': {'name': f'Alice {index}'}, 'player2': {'name': f'Bob {index}'},
            })
            return self.advance(state, client, random.Random(index), 4 + index % 5)
        with ThreadPoolExecutor(max_workers=10) as pool:
            states = list(pool.map(play, range(100)))
        self.assertEqual(len({s['game_id'] for s in states}), 100)
        restarted = TestClient(server.create_app(self.path))
        for index, state in enumerate(states):
            self.assertEqual(restarted.get('/api/game/' + state['game_id']).json(), state)
            saved = self.store.load(state['game_id'])
            self.assertEqual(saved.players['player1']['name'], f'Alice {index}')
            self.assertEqual(len(saved.moves), state['version'])
            self.assertEqual(sum(saved.game.board.holes) + saved.game.score_p1 + saved.game.score_p2, 48)

    def test_invalid_identifiers_turns_and_versions_never_change_either_game(self):
        first, second = self.start(), self.start()
        first = self.move(first).json()
        snapshots = {s['game_id']: _encode(self.store.load(s['game_id'])) for s in (first, second)}
        payload = {'game_id': first['game_id'], 'version': first['version'],
                   'player': first['current_player'], 'pit_index': first['valid_moves'][0]}
        cases = [({'game_id': str(uuid4())}, 404), ({'game_id': 'broken'}, 422),
                 ({'game_id': None}, 422), ({'version': 0}, 409), ({'version': 99}, 409),
                 ({'player': 'player1'}, 400), ({'pit_index': 99}, 422), ({'pit_index': True}, 422)]
        for changes, status in cases:
            with self.subTest(changes=changes):
                response = self.client.post('/api/game/move', json=dict(payload, **changes))
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.headers['cache-control'], 'no-store')
                for game_id, snapshot in snapshots.items():
                    self.assertEqual(_encode(self.store.load(game_id)), snapshot)
        missing = dict(payload)
        del missing['game_id']
        self.assertEqual(self.client.post('/api/game/move', json=missing).status_code, 422)

    def test_storage_refuses_saving_another_games_snapshot_and_version_reuse(self):
        first, second = self.start(), self.start()
        foreign = self.store.load(second['game_id'])
        foreign.game.play_move(0)
        with self.assertRaises(StorageError):
            self.store.save(first['game_id'], foreign, 0, server.SESSION_TTL)
        unchanged = self.store.load(first['game_id'])
        with self.assertRaises(VersionConflict):
            self.store.save(first['game_id'], unchanged, 0, server.SESSION_TTL)
        self.assertEqual(self.client.get('/api/game/' + first['game_id']).json(), first)
        self.assertEqual(self.client.get('/api/game/' + second['game_id']).json(), second)

    def test_duplicate_uuid_never_overwrites_an_existing_game(self):
        first = self.start()
        with patch('api.server.uuid4', return_value=first['game_id']):
            with self.assertLogs('api.server', level='ERROR'):
                response = self.client.post('/api/game/start', json={'player1': {}, 'player2': {}})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.client.get('/api/game/' + first['game_id']).json(), first)

    def test_ai_player_parameters_and_move_history_survive_restart_separately(self):
        states = []
        for agent, depth, name in [('minimax', 2, 'Alice'), ('alphabeta', 3, 'Bob')]:
            state = self.start(players={'player1': {'name': name, 'type': 'ai', 'agent': agent, 'depth': depth},
                                        'player2': {'name': name + ' 2', 'type': 'human'}})
            response = self.client.post('/api/game/ai-move', json={
                'game_id': state['game_id'], 'version': 0, 'player': 'player1', 'agent': agent, 'depth': depth,
            })
            self.assertEqual(response.status_code, 200)
            states.append((response.json()['game_state'], agent, depth, name))
        restarted = SQLiteSessionStore(self.path)
        for state, agent, depth, name in states:
            restored = restarted.load(state['game_id'])
            self.assertEqual(restored.players['player1'], {'name': name, 'type': 'ai', 'agent': agent, 'depth': depth})
            self.assertEqual(restored.moves, self.store.load(state['game_id']).moves)
            self.assertEqual(server._game_to_state(restored.game, state['game_id']), state)

    def test_two_processes_racing_the_same_version_commit_exactly_one_move(self):
        state = self.start()
        code = """
import json, sys
from api import server
from fastapi.testclient import TestClient
check = server._check_turn
def synchronize(*args):
    check(*args)
    print('ready', flush=True)
    assert sys.stdin.readline().strip() == 'go'
server._check_turn = synchronize
response = TestClient(server.app).post('/api/game/move', json=json.loads(sys.argv[1]))
print(json.dumps({'status': response.status_code, 'body': response.json()}), flush=True)
"""
        payload = json.dumps({'game_id': state['game_id'], 'version': 0,
                              'player': 'player1', 'pit_index': 0})
        processes = []
        try:
            for _ in range(2):
                processes.append(subprocess.Popen(
                    [sys.executable, '-B', '-X', 'utf8', '-c', code, payload],
                    cwd=Path(__file__).resolve().parents[1],
                    env=dict(os.environ, AWALE_DB_PATH=str(self.path)),
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, encoding='utf-8', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                ))
            # Both requests have loaded and validated version zero before either saves.
            with ThreadPoolExecutor(max_workers=2) as pool:
                readiness = [pool.submit(p.stdout.readline) for p in processes]
                for ready in readiness:
                    self.assertEqual(ready.result(timeout=15).strip(), 'ready')
                results = list(pool.map(lambda p: p.communicate(input='go\n', timeout=15), processes))
            responses = []
            for process, (output, error) in zip(processes, results):
                self.assertEqual(process.returncode, 0, error)
                responses.append(json.loads(output))
            self.assertEqual(sorted(r['status'] for r in responses), [200, 409])
            saved = self.store.load(state['game_id'])
            self.assertEqual(saved.game.plies, 1)
            self.assertEqual(len(saved.moves), 1)
            self.assertEqual(self.client.get('/api/game/' + state['game_id']).json(),
                             next(r['body'] for r in responses if r['status'] == 200))
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=5)

    def test_real_http_clients_play_simultaneously_on_a_separate_backend_process(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
        with tempfile.TemporaryFile(mode='w+', encoding='utf-8') as log:
            process = subprocess.Popen(
                [sys.executable, '-B', '-X', 'utf8', '-m', 'uvicorn', 'api.server:app',
                 '--host', '127.0.0.1', '--port', str(port)],
                cwd=Path(__file__).resolve().parents[1],
                env=dict(os.environ, AWALE_DB_PATH=str(self.path)),
                stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
            try:
                with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=5) as first_client:
                    with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=5) as second_client:
                        deadline = time.monotonic() + 15
                        while time.monotonic() < deadline and process.poll() is None:
                            try:
                                if first_client.get('/').status_code == 200:
                                    break
                            except httpx.RequestError:
                                pass
                            time.sleep(0.05)
                        else:
                            log.seek(0)
                            self.fail('Backend did not start: ' + log.read())
                        first_client.cookies.set('session', 'phone-a')
                        second_client.cookies.set('session', 'phone-b')
                        states = [self.start(client=first_client), self.start(client=second_client)]
                        clients = [first_client, second_client]
                        with ThreadPoolExecutor(max_workers=2) as pool:
                            futures = [pool.submit(self.advance, state, client, random.Random(index + 3), 15)
                                       for index, (state, client) in enumerate(zip(states, clients))]
                            states = [f.result(timeout=15) for f in futures]
                        for state, client in zip(states, clients):
                            response = client.get('/api/game/' + state['game_id'])
                            self.assertEqual(response.json(), state)
                            self.assertEqual(response.headers['cache-control'], 'no-store')
                            self.assertEqual(self.client.get('/api/game/' + state['game_id']).json(), state)
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)

    def test_legacy_schema_one_snapshot_without_move_list_still_loads(self):
        state = self.start()
        payload = json.loads(self.row(state['game_id'])['state'])
        del payload['moves']
        for player in payload['players'].values():
            player.pop('agent', None)
            player.pop('depth', None)
        with self.connection() as connection:
            connection.execute('UPDATE sessions SET state = ? WHERE game_id = ?',
                               (json.dumps(payload), state['game_id']))
        self.assertEqual(self.client.get('/api/game/' + state['game_id']).json(), state)
        self.assertEqual(self.move(state).status_code, 200)
        self.assertEqual(len(self.store.load(state['game_id']).moves), 1)

