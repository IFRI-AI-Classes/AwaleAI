"""Transactional SQLite storage for complete, restartable game sessions."""

from contextlib import closing, contextmanager
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import sqlite3
from threading import Lock
import time
from weakref import WeakValueDictionary

from engine.game import Game


class StorageError(Exception):
    """The database or a stored session cannot be used safely."""


class SessionNotFound(Exception):
    pass


class VersionConflict(Exception):
    pass


class SessionCapacity(Exception):
    pass


@dataclass
class Session:
    game: Game
    players: dict
    expires_at: float
    game_id: str
    lock: object = field(default_factory=Lock, repr=False, compare=False)
    moves: list = field(default_factory=list)


def _position(holes, score1, score2, player):
    """Validate persisted data without changing the engine's rules."""
    if (not isinstance(holes, list) or len(holes) != 12
            or any(type(n) is not int or not 0 <= n <= 48 for n in holes)
            or any(type(n) is not int or not 0 <= n <= 48 for n in (score1, score2))
            or type(player) is not int or player not in (1, 2)
            or sum(holes) + score1 + score2 != 48):
        raise ValueError("Position persistée invalide.")
    return tuple(holes), score1, score2, player


def _encode(session):
    game = session.game
    return json.dumps({
        "schema_version": 1,
        "players": session.players,
        "moves": session.moves,
        "game": {
            "holes": game.board.holes,
            "score_p1": game.score_p1,
            "score_p2": game.score_p2,
            "current_player": game.current_player,
            "plies": game.plies,
            "max_plies": game.max_plies,
            "history": sorted(game._history),
            "repeated": game._repeated,
        },
    }, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _decode(row, lock):
    try:
        payload = json.loads(row["state"])
        if (not isinstance(row["expires_at"], (int, float))
                or not math.isfinite(row["expires_at"])):
            raise ValueError("Expiration persistée invalide.")
        if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
            raise ValueError("Version de sauvegarde inconnue.")
        players = payload["players"]
        if not isinstance(players, dict) or set(players) != {"player1", "player2"}:
            raise ValueError("Joueurs persistés invalides.")
        for player in players.values():
            if (not isinstance(player, dict) or not isinstance(player["name"], str)
                    or len(player["name"]) > 80 or player["type"] not in ("human", "ai")):
                raise ValueError("Configuration persistée invalide.")
            agent, depth = player.get("agent"), player.get("depth")
            if (agent is not None and agent not in ("random", "minimax", "alphabeta", "qlearning")
                    or depth is not None and (type(depth) is not int
                    or agent == "minimax" and not 1 <= depth <= 8
                    or agent == "alphabeta" and not 1 <= depth <= 12)):
                raise ValueError("Paramètres IA persistés invalides.")
        data = payload["game"]
        _position(data["holes"], data["score_p1"], data["score_p2"], data["current_player"])
        if (type(data["plies"]) is not int or data["plies"] < 0
                or data["plies"] != row["version"] or type(data["repeated"]) is not bool
                or not isinstance(data["history"], list) or not data["history"]):
            raise ValueError("Historique ou version persistés invalides.")
        history = {_position(*position) for position in data["history"]}
        game = Game(max_plies=data["max_plies"])
        game.board.holes = data["holes"]
        game.score_p1, game.score_p2 = data["score_p1"], data["score_p2"]
        game.current_player = data["current_player"]
        game.plies = data["plies"]
        game._history = history
        game._repeated = data["repeated"]
        if game.position_key() not in history:
            raise ValueError("Position absente de l'historique persisté.")
        moves = payload.get("moves", [])
        if not isinstance(moves, list):
            raise ValueError("Historique des coups persisté invalide.")
        last_version = 0
        for move in moves:
            if (not isinstance(move, dict) or type(move["version"]) is not int
                    or not last_version < move["version"] <= game.plies
                    or move["player"] not in ("player1", "player2")
                    or type(move["pit_index"]) is not int or not 0 <= move["pit_index"] <= 11):
                raise ValueError("Coup persisté invalide.")
            last_version = move["version"]
        return Session(game, players, row["expires_at"], row["game_id"], lock, moves)
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        raise StorageError("La sauvegarde de la partie est invalide.") from exc


class SQLiteSessionStore:
    """Use fresh connections and compare versions inside short transactions.

    Runtime locks serialize a game's requests in one application instance.
    SQLite version checks also prevent lost updates between application instances.
    No game cache is kept, so a failed commit cannot leave an advanced board in memory.
    """

    def __init__(self, path, timeout=5.0):
        if str(path) == ":memory:":
            raise ValueError("Le stockage des parties exige un fichier SQLite.")
        self.path = Path(path).resolve()
        self.timeout = timeout
        self._locks = WeakValueDictionary()
        self._locks_guard = Lock()

    def lock_for(self, game_id):
        key = str(game_id)
        with self._locks_guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = Lock()
                self._locks[key] = lock
            return lock

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=self.timeout, isolation_level=None)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("""CREATE TABLE IF NOT EXISTS sessions (
                game_id TEXT PRIMARY KEY,
                version INTEGER NOT NULL,
                expires_at REAL NOT NULL,
                state TEXT NOT NULL
            )""")
            return connection
        except BaseException:
            connection.close()
            raise

    @contextmanager
    def _transaction(self):
        try:
            with closing(self._connect()) as connection:
                with connection:
                    connection.execute("BEGIN IMMEDIATE")
                    yield connection
        except (sqlite3.Error, OSError) as exc:
            raise StorageError("SQLite est indisponible.") from exc

    @staticmethod
    def _write_session(connection, game_id, session, expected_version=None):
        state = _encode(session)
        if expected_version is None:
            connection.execute(
                "INSERT INTO sessions (game_id, version, expires_at, state) VALUES (?, ?, ?, ?)",
                (str(game_id), session.game.plies, session.expires_at, state),
            )
        else:
            result = connection.execute(
                "UPDATE sessions SET version = ?, expires_at = ?, state = ? "
                "WHERE game_id = ? AND version = ?",
                (session.game.plies, session.expires_at, state, str(game_id), expected_version),
            )
            if result.rowcount != 1:
                raise VersionConflict()

    def create(self, game_id, game, players, ttl, capacity):
        session = Session(game, players, time.time() + ttl, str(game_id), self.lock_for(game_id))
        with self._transaction() as connection:
            connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (time.time(),))
            if connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] >= capacity:
                raise SessionCapacity()
            self._write_session(connection, game_id, session)
        return session

    def load(self, game_id, ttl=None):
        """Restore the complete state and optionally renew inactivity expiration."""
        with self._transaction() as connection:
            now = time.time()
            row = connection.execute(
                "SELECT * FROM sessions WHERE game_id = ? AND expires_at > ?",
                (str(game_id), now),
            ).fetchone()
            if row is None:
                raise SessionNotFound()
            session = _decode(row, self.lock_for(game_id))
            if ttl is not None:
                session.expires_at = now + ttl
                connection.execute("UPDATE sessions SET expires_at = ? WHERE game_id = ?",
                                   (session.expires_at, str(game_id)))
        return session

    def save(self, game_id, session, expected_version, ttl):
        if str(game_id) != session.game_id:
            raise StorageError("La sauvegarde ne correspond pas à cette partie.")
        if (type(expected_version) is not int or expected_version < 0
                or session.game.plies != expected_version + 1):
            raise VersionConflict()
        with self._transaction() as connection:
            now = time.time()
            row = connection.execute(
                "SELECT version FROM sessions WHERE game_id = ? AND expires_at > ?",
                (str(game_id), now),
            ).fetchone()
            if row is None:
                raise SessionNotFound()
            if row["version"] != expected_version:
                raise VersionConflict()
            session.expires_at = now + ttl
            self._write_session(connection, game_id, session, expected_version)

    def check(self):
        with self._transaction() as connection:
            connection.execute("SELECT game_id, version, expires_at, state FROM sessions LIMIT 1").fetchone()
