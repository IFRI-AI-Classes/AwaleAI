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

    Args:
        game: Active Awalé game instance.

    Returns:
        dict: Serialized game state.
    """
    return {
        "board": list(game.board.holes),
        "scores": {
            "player1": game.score_p1,
            "player2": game.score_p2,
        },
        "granaries": {
            "player1": game.score_p1,
            "player2": game.score_p2,
        },
        "current_player": "player1" if game.current_player == 1 else "player2",
        "game_over": game.is_game_over(),
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
        level: AI difficulty level when applicable.
    """

    name: str = "Joueur"
    type: str = "human"
    level: Optional[str] = None


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
        level: Difficulty level requested by the client.
        board: Client-side board snapshot kept for compatibility.
    """

    player: str
    level: str
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


@app.post("/api/game/ai-move")
def ai_move(req: AIMoveRequest):
    """
    Play an AI move for the current game.

    Uses the difficulty routing defined in agents.difficulty to select the
    appropriate agent and search depth for the requested level.

    Args:
        req: Acting player, requested level, and compatibility board payload.

    Returns:
        dict: Updated game state and telemetry payload.

    Raises:
        HTTPException: If no game is active, the game is over, the requested
            level is unknown, or the AI cannot find a legal move.
    """
    global _game

    if _game is None:
        raise HTTPException(
            status_code=400,
            detail="Aucune partie en cours. Appelez /api/game/start d'abord.",
        )

    if _game.is_game_over():
        raise HTTPException(status_code=400, detail="La partie est terminée.")

    level = req.level.lower()

    if level not in difficulty.LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"Niveau inconnu : '{req.level}'. Niveaux disponibles : {list(difficulty.LEVELS.keys())}",
        )

    config = difficulty.LEVELS[level]
    depth_used = config["depth"]

    start_time = time.time()
    hole = difficulty.choose_move(_game, level)
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
        "nodes_explored": None,
        "win_rate": None,
        "level": level,
        "agent": config["agent"],
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
