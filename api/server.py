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

# ─── Session de jeu unique en mémoire ───────────────────────────────────────
_game: Optional[Game] = None
_player_configs: dict = {}


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _game_to_state(game: Game) -> dict:
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
    if not game.is_game_over():
        return None
    winner = game.get_winner()
    if winner == 1:
        return "player1"
    if winner == 2:
        return "player2"
    return None


def _player_key_to_int(key: str) -> int:
    return 1 if key == "player1" else 2


# ─── Schémas Pydantic ─────────────────────────────────────────────────────────

class PlayerConfig(BaseModel):
    name: str = "Joueur"
    type: str = "human"          # "human" | "ai"
    level: Optional[str] = None  # "facile" | "moyen" | "difficile" | "expert"


class StartRequest(BaseModel):
    player1: PlayerConfig
    player2: PlayerConfig


class MoveRequest(BaseModel):
    pit_index: int
    player: str


class AIMoveRequest(BaseModel):
    player: str
    level: str  # ← anciennement "algorithm", renommé pour refléter le vrai contenu
    board: list[int]  # non utilisé directement (on utilise _game)


# ─── Endpoints ───────────────────────────────────────────────────────────────

@app.post("/api/game/start")
def start_game(req: StartRequest):
    global _game, _player_configs

    _game = Game()
    _player_configs = {
        "player1": req.player1.model_dump(),
        "player2": req.player2.model_dump(),
    }

    return _game_to_state(_game)


@app.post("/api/game/move")
def human_move(req: MoveRequest):
    global _game

    if _game is None:
        raise HTTPException(status_code=400, detail="Aucune partie en cours. Appelez /api/game/start d'abord.")

    if _game.is_game_over():
        raise HTTPException(status_code=400, detail="La partie est terminée.")

    expected_player = "player1" if _game.current_player == 1 else "player2"
    if req.player != expected_player:
        raise HTTPException(
            status_code=400,
            detail=f"Ce n'est pas le tour de {req.player}. C'est le tour de {expected_player}."
        )

    valid_moves = Rules.get_valid_moves(_game.board, _game.current_player)
    if req.pit_index not in valid_moves:
        raise HTTPException(
            status_code=400,
            detail=f"Coup invalide. Coups valides : {valid_moves}"
        )

    _game.play_move(req.pit_index)
    return _game_to_state(_game)


@app.post("/api/game/ai-move")
def ai_move(req: AIMoveRequest):
    """
    Fait jouer l'IA selon le NIVEAU demandé (facile/moyen/difficile/expert).
    Toute la logique d'aiguillage vers le bon agent + profondeur vit dans
    agents/difficulty.py — server.py ne fait que la consulter.
    """
    global _game

    if _game is None:
        raise HTTPException(status_code=400, detail="Aucune partie en cours. Appelez /api/game/start d'abord.")

    if _game.is_game_over():
        raise HTTPException(status_code=400, detail="La partie est terminée.")

    level = req.level.lower()

    if level not in difficulty.LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"Niveau inconnu : '{req.level}'. Niveaux disponibles : {list(difficulty.LEVELS.keys())}"
        )

    config = difficulty.LEVELS[level]
    depth_used = config["depth"]  # None pour "facile" (random)

    start_time = time.time()
    hole = difficulty.choose_move(_game, level)
    elapsed_ms = round((time.time() - start_time) * 1000, 1)

    if hole is None:
        raise HTTPException(status_code=400, detail="L'IA n'a trouvé aucun coup valide.")

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


# ─── Health check ─────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"status": "ok", "project": "AwaleAI"}