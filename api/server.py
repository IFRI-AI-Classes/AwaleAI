"""FastAPI endpoints with isolated, versioned in-memory game sessions."""
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Annotated, Literal, Optional
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from engine.game import Game
from agents import difficulty
from agents.difficulty import AGENTS

app = FastAPI(title="AwaleAI API", version="1.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Local development: run a single ASGI worker. Sessions expire after inactivity.
SESSION_TTL = 3600
MAX_SESSIONS = 256


@dataclass
class Session:
    game: Game
    players: dict
    last_used: float = field(default_factory=time.monotonic)
    lock: Lock = field(default_factory=Lock)


_sessions: dict[str, Session] = {}
_sessions_lock = Lock()


def _expire_sessions(now):
    for key in list(_sessions):
        session = _sessions[key]
        if now - session.last_used > SESSION_TTL and session.lock.acquire(blocking=False):
            try:
                del _sessions[key]
            finally:
                session.lock.release()


def _get_session(game_id):
    key = str(game_id)
    with _sessions_lock:
        now = time.monotonic()
        _expire_sessions(now)
        session = _sessions.get(key)
        if session is None:
            raise HTTPException(status_code=404, detail="Partie introuvable ou expirée.")
        session.last_used = now
        return session


def _get_winner_key(game):
    winner = game.get_winner()
    return f"player{winner}" if winner is not None else None


def _game_to_state(game, game_id=None):
    s1, s2 = game.final_scores()
    return {
        "game_id": str(game_id) if game_id is not None else None,
        "version": game.plies,
        "board": list(game.board.holes),
        "scores": {"player1": s1, "player2": s2},
        "granaries": {"player1": s1, "player2": s2},
        "current_player": f"player{game.current_player}",
        "game_over": game.is_game_over(),
        "end_reason": game.end_reason(),
        "winner": _get_winner_key(game),
        "valid_moves": game.get_valid_moves(),
    }


PlayerKey = Literal["player1", "player2"]
Seed = Annotated[int, Field(strict=True, ge=0, le=48)]


class PlayerConfig(BaseModel):
    name: str = Field(default="Joueur", max_length=80)
    type: Literal["human", "ai"] = "human"


class StartRequest(BaseModel):
    player1: PlayerConfig
    player2: PlayerConfig


class MoveRequest(BaseModel):
    game_id: UUID
    version: int = Field(strict=True, ge=0)
    pit_index: int = Field(strict=True, ge=0, le=11)
    player: PlayerKey


class AIMoveRequest(BaseModel):
    game_id: UUID
    version: int = Field(strict=True, ge=0)
    player: PlayerKey
    agent: str
    depth: Optional[int] = Field(default=None, strict=True)
    board: Optional[list[Seed]] = Field(default=None, min_length=12, max_length=12)


def _check_turn(session, req, player_type):
    game = session.game
    if req.version != game.plies:
        raise HTTPException(status_code=409, detail="Le plateau a changé. Ce coup est périmé.")
    if game.is_game_over():
        raise HTTPException(status_code=400, detail="La partie est terminée.")
    expected = f"player{game.current_player}"
    if req.player != expected:
        raise HTTPException(status_code=400, detail=f"C'est le tour de {expected}.")
    if session.players[req.player]["type"] != player_type:
        raise HTTPException(status_code=400, detail="Le type du joueur ne correspond pas à ce coup.")


@app.post("/api/game/start")
def start_game(req: StartRequest):
    key = str(uuid4())
    session = Session(Game(), {
        "player1": req.player1.model_dump(),
        "player2": req.player2.model_dump(),
    })
    with _sessions_lock:
        _expire_sessions(time.monotonic())
        if len(_sessions) >= MAX_SESSIONS:
            raise HTTPException(status_code=503, detail="Trop de parties actives. Réessayez plus tard.")
        _sessions[key] = session
    return _game_to_state(session.game, key)


@app.get("/api/game/{game_id}")
def get_game(game_id: UUID):
    session = _get_session(game_id)
    with session.lock:
        return _game_to_state(session.game, game_id)


@app.post("/api/game/move")
def human_move(req: MoveRequest):
    session = _get_session(req.game_id)
    with session.lock:
        _check_turn(session, req, "human")
        if not session.game.play_move(req.pit_index):
            raise HTTPException(status_code=400, detail="Coup invalide.")
        session.last_used = time.monotonic()
        return _game_to_state(session.game, req.game_id)


@app.get("/api/agents")
def get_agents():
    return {"agents": AGENTS}


@app.post("/api/game/ai-move")
def ai_move(req: AIMoveRequest):
    session = _get_session(req.game_id)
    with session.lock:
        _check_turn(session, req, "ai")
        game = session.game
        if req.board is not None and req.board != game.board.holes:
            raise HTTPException(status_code=409, detail="Le plateau envoyé est périmé.")
        agent = req.agent.lower()
        try:
            depth = difficulty.effective_depth(agent, req.depth)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        start = time.perf_counter()
        hole, nodes = difficulty.choose_move_by_agent(game, agent, depth)
        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        if not game.play_move(hole):
            raise HTTPException(status_code=500, detail="L'IA a renvoyé un coup invalide.")
        session.last_used = time.monotonic()
        return {
            "game_state": _game_to_state(game, req.game_id),
            "telemetry": {
                "computation_time": elapsed_ms,
                "depth": depth,
                "nodes_explored": nodes,
                "win_rate": None,
                "pit_played": hole,
                "agent": agent,
            },
        }


@app.get("/")
def root():
    return {"status": "ok", "project": "AwaleAI"}
