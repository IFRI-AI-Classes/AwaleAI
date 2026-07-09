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
from agents.alpha_beta.elagage import best_move as alpha_beta_move
from agents.minimax.minimax import Minimax
from agents.random.random_agent import random_move

app = FastAPI(title="AwaleAI API", version="1.0.0")

# Autoriser le frontend local (fichier ou serveur de dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Session de jeu unique en mémoire ───────────────────────────────────────
# Pour une démo mono-utilisateur ; étendre avec un dict de sessions si besoin.
_game: Optional[Game] = None
_player_configs: dict = {}

MINIMAX_DEPTH    = 7
ALPHABETA_DEPTH  = 7


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _game_to_state(game: Game) -> dict:
    """Sérialise l'état courant du jeu au format attendu par app.js."""
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
    """Retourne 'player1', 'player2' ou None si la partie n'est pas terminée."""
    if not game.is_game_over():
        return None
    winner = game.get_winner()
    if winner == 1:
        return "player1"
    if winner == 2:
        return "player2"
    return None  # égalité


def _player_key_to_int(key: str) -> int:
    return 1 if key == "player1" else 2


# ─── Schémas Pydantic ─────────────────────────────────────────────────────────

class PlayerConfig(BaseModel):
    name: str = "Joueur"
    type: str = "human"          # "human" | "ai"
    algorithm: Optional[str] = None  # "random" | "minimax" | "alphabeta" | "qlearning"


class StartRequest(BaseModel):
    player1: PlayerConfig
    player2: PlayerConfig


class MoveRequest(BaseModel):
    pit_index: int
    player: str   # "player1" | "player2"


class AIMoveRequest(BaseModel):
    player: str
    algorithm: str
    board: list[int]  # non utilisé directement (on utilise _game), fourni par le front


# ─── Endpoints ───────────────────────────────────────────────────────────────

@app.post("/api/game/start")
def start_game(req: StartRequest):
    """
    Démarre une nouvelle partie.
    Stocke la configuration des joueurs et retourne l'état initial.
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
    """
    Applique le coup d'un joueur humain.
    Retourne le nouvel état du jeu.
    """
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
    Fait jouer l'IA selon l'algorithme demandé.
    Retourne le nouvel état + la télémétrie (temps, profondeur, nœuds si disponible).
    """
    global _game

    if _game is None:
        raise HTTPException(status_code=400, detail="Aucune partie en cours. Appelez /api/game/start d'abord.")

    if _game.is_game_over():
        raise HTTPException(status_code=400, detail="La partie est terminée.")

    algorithm = req.algorithm.lower()
    depth_used = None
    nodes_explored = None

    start_time = time.time()

    if algorithm == "random":
        hole = random_move(_game)

    elif algorithm == "minimax":
        depth_used = MINIMAX_DEPTH
        agent = Minimax(depth=depth_used)
        hole = agent.choose_move(_game.board, player=_game.current_player)

    elif algorithm == "alphabeta":
        depth_used = ALPHABETA_DEPTH
        hole = alpha_beta_move(_game, depth=depth_used)

    elif algorithm == "qlearning":
        # Phase 3 non implémentée : repli sur l'agent aléatoire
        hole = random_move(_game)
        algorithm = "random (qlearning not yet implemented)"

    else:
        raise HTTPException(status_code=400, detail=f"Algorithme inconnu : {req.algorithm}")

    if hole is None:
        raise HTTPException(status_code=400, detail="L'IA n'a trouvé aucun coup valide.")

    elapsed_ms = round((time.time() - start_time) * 1000, 1)

    pit_played = hole
    _game.play_move(hole)

    telemetry = {
        "computation_time": elapsed_ms,
        "depth": depth_used,
        "nodes_explored": nodes_explored,
        "win_rate": None,
        "algorithm": algorithm,
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
