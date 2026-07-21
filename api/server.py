"""
Backend FastAPI pour AwaleAI.

Expose trois endpoints attendus par web/app.js :
  POST /api/game/start    → démarre une partie, retourne l'état initial
  POST /api/game/move     → applique un coup humain, retourne le nouvel état
  POST /api/game/ai-move  → fait jouer l'IA, retourne état + télémétrie

Lancement :
    uvicorn api.server:app --reload --port 8000
"""

import time
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from engine.game import Game
from engine.rules import Rules
from agents import difficulty  # ← module centralisé niveau → agent/profondeur
from agents.difficulty import AGENTS

app = FastAPI(title="AwaleAI API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session de jeu unique en mémoire
_game: Optional[Game] = None
_player_configs: dict = {}


# Helpers


def _game_to_state(game: Game) -> dict:
    """Convert a game instance into the API response payload.

    When the game is over and ended by blocking (no valid moves), the remaining
    seeds on the board belong to the opponent of the blocked player. We compute
    the final scores here so the frontend always receives the correct totals.

    Args:
        game: Active Awalé game instance.

    Returns:
        dict: Serialized game state.
    """
    game_over = game.is_game_over()

    # Compute final scores without mutating game state.
    # Centralise the residual-seeds logic in one place: when the game ends by
    # blockade (current player has no move) the remaining seeds on the board
    # belong to the opponent.  This mirrors exactly what get_winner() does.
    s1, s2 = game.score_p1, game.score_p2
    if game_over and not Rules.get_valid_moves(game.board, game.current_player):
        remaining = sum(game.board.holes)
        if game.current_player == 1:
            s2 += remaining
        else:
            s1 += remaining
    # When game ends by score (>= 25) there are no residual seeds to award;
    # s1/s2 are already the correct final values.

    return {
        "board": list(game.board.holes),
        "scores": {
            "player1": s1,
            "player2": s2,
        },
        "granaries": {
            "player1": s1,
            "player2": s2,
        },
        "current_player": "player1" if game.current_player == 1 else "player2",
        "game_over": game_over,
        "winner": _get_winner_key(game),
        "valid_moves": Rules.get_valid_moves(game.board, game.current_player),
    }


def _get_winner_key(game: Game) -> Optional[str]:
    """Return the API winner key for the current game state.

    Args:
        game: Active Awalé game instance.

    Returns:
        Optional[str]: "player1", "player2", or None if the game is ongoing.
    """
    if not game.is_game_over():
        return None
    winner = game.get_winner()
    if winner == 1:
        return "player1"
    if winner == 2:
        return "player2"
    return None


def _player_key_to_int(key: str) -> int:
    """Map an API player key to the internal player index.

    Args:
        key: Player identifier used by the API.

    Returns:
        int: Internal player index.
    """
    return 1 if key == "player1" else 2


# Pydantic schemas


class PlayerConfig(BaseModel):
    """Player configuration provided by the client.

    Attributes:
        name: Human-readable player name.
        type: Player type, either human or AI.
    """

    name: str = "Joueur"
    type: str = "human"


class StartRequest(BaseModel):
    """Request payload used to start a new game.

    Attributes:
        player1: Configuration for player1.
        player2: Configuration for player2.
    """

    player1: PlayerConfig
    player2: PlayerConfig


class MoveRequest(BaseModel):
    """Request payload for a human move.

    Attributes:
        pit_index: Selected pit index.
        player: Player key expected to act.
    """

    pit_index: int
    player: str


class AIMoveRequest(BaseModel):
    """Request payload for an AI move.

    Attributes:
        player: Player key expected to act.
        agent: Agent identifier (random, minimax, alphabeta, qlearning).
        depth: Search depth. None for agents that do not use it.
        board: Client-side board snapshot kept for compatibility.
    """

    player: str
    agent: str
    depth: Optional[int] = None
    board: list[int]


# Endpoints


@app.post("/api/game/start")
def start_game(req: StartRequest):
    """Start a new Awalé game.

    Initializes a fresh in-memory game instance and stores the player
    configuration for the current session.

    Args:
        req: Player configuration for both sides.

    Returns:
        dict: Initial game state payload.
    """
    global _game, _player_configs

    _game = Game()
    _player_configs = {
        "player1": req.player1.model_dump(),
        "player2": req.player2.model_dump(),
    }

    return _game_to_state(_game)


@app.post("/api/game/move")
def human_move(req: MoveRequest):
    """Apply a human move to the current game.

    Args:
        req: Selected pit index and acting player key.

    Returns:
        dict: Updated game state payload.

    Raises:
        HTTPException: If no game is active, the game is over, the wrong
            player acts, or the selected pit is invalid.
    """
    global _game

    if _game is None:
        raise HTTPException(
            status_code=400,
            detail="Aucune partie en cours. Appelez /api/game/start d'abord.",
        )

    if _game.is_game_over():
        raise HTTPException(status_code=400, detail="La partie est terminée.")

    expected_player = "player1" if _game.current_player == 1 else "player2"
    if req.player != expected_player:
        raise HTTPException(
            status_code=400,
            detail=f"Ce n'est pas le tour de {req.player}. C'est le tour de {expected_player}.",
        )

    valid_moves = Rules.get_valid_moves(_game.board, _game.current_player)
    if req.pit_index not in valid_moves:
        raise HTTPException(
            status_code=400, detail=f"Coup invalide. Coups valides : {valid_moves}"
        )

    _game.play_move(req.pit_index)
    return _game_to_state(_game)


@app.get("/api/agents")
def get_agents():
    """Return the list of available AI agents and their depth ranges.

    Returns:
        dict: Agent metadata keyed by agent identifier.
    """
    return {"agents": AGENTS}


@app.post("/api/game/ai-move")
def ai_move(req: AIMoveRequest):
    """Play an AI move for the current game.

    The caller specifies the agent and depth directly. The server selects the
    move using agents.difficulty.choose_move_by_agent.

    Args:
        req: Acting player, agent identifier, depth, and compatibility board.

    Returns:
        dict: Updated game state and telemetry payload.

    Raises:
        HTTPException: If no game is active, the game is over, the agent is
            unknown, or the AI cannot find a legal move.
    """
    global _game

    if _game is None:
        raise HTTPException(
            status_code=400,
            detail="Aucune partie en cours. Appelez /api/game/start d'abord.",
        )

    if _game.is_game_over():
        raise HTTPException(status_code=400, detail="La partie est terminée.")

    agent = req.agent.lower()

    if agent not in AGENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Agent inconnu : '{req.agent}'. Agents disponibles : {list(AGENTS.keys())}",
        )

    depth_used = req.depth

    start_time = time.time()
    hole, nodes_explored = difficulty.choose_move_by_agent(_game, agent, depth_used)
    elapsed_ms = round((time.time() - start_time) * 1000, 1)

    if hole is None:
        raise HTTPException(
            status_code=400, detail="L'IA n'a trouvé aucun coup valide."
        )

    pit_played = hole
    _game.play_move(hole)

    telemetry = {
        "computation_time": elapsed_ms,
        "depth": depth_used,
        "nodes_explored": nodes_explored,
        "win_rate": None,
        "agent": agent,
        "pit_played": pit_played,
    }

    return {
        "game_state": _game_to_state(_game),
        "telemetry": telemetry,
    }


# Health check


@app.get("/")
def root():
    """Return a lightweight health check response.

    Returns:
        dict: Service status and project name.
    """
    return {"status": "ok", "project": "AwaleAI"}
