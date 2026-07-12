# agents/difficulty.py
"""
Module central de gestion des niveaux de difficulté.

Objectif : offrir UN SEUL point d'entrée — choose_move(game, level) —
que main.py ET server.py pourront appeler, sans dupliquer la logique
de sélection d'agent.
"""

from agents.random.random_agent import random_move
from agents.minimax.minimax import Minimax
from agents.alpha_beta.elagage import best_move as alpha_beta_move


# ─────────────────────────────────────────────────────────────────
# Étape 1 : dictionnaire de configuration des niveaux
# ─────────────────────────────────────────────────────────────────
# Chaque niveau précise :
#   - "agent"  : quel algorithme utiliser ("random", "minimax", "alphabeta")
#   - "depth"  : la profondeur de recherche (None si non applicable, ex: random)
#
# C'est la SEULE partie que tu dois modifier si tu veux ajuster
# l'équilibrage des niveaux (par exemple rendre "difficile" plus fort).
LEVELS = {
    "facile": {
        "agent": "random",
        "depth": None,
    },
    "moyen": {
        "agent": "minimax",
        "depth": 2,
    },
    "difficile": {
        "agent": "alphabeta",
        "depth": 5,
    },
    "expert": {
        "agent": "alphabeta",
        "depth": 8,
    },
}


# ─────────────────────────────────────────────────────────────────
# Étape 2 : la fonction unique qui redirige vers le bon agent
# ─────────────────────────────────────────────────────────────────
def choose_move(game, level: str) -> int:
    """
    Retourne l'indice (0-11) de la case à jouer, en fonction du niveau
    de difficulté demandé.

    Args:
        game (Game): l'état actuel de la partie.
        level (str): "facile", "moyen", "difficile" ou "expert".

    Returns:
        int: indice de la case choisie par l'agent IA.

    Raises:
        ValueError: si le niveau demandé n'existe pas.
    """
    if level not in LEVELS:
        raise ValueError(
            f"Niveau inconnu : '{level}'. "
            f"Niveaux disponibles : {list(LEVELS.keys())}"
        )

    config = LEVELS[level]
    agent_name = config["agent"]
    depth = config["depth"]

    # --- Cas 1 : agent aléatoire ---
    # random_move attend directement l'objet 'game'.
    if agent_name == "random":
        return random_move(game)

    # --- Cas 2 : Minimax ---
    # Minimax.choose_move attend (board, player), pas 'game' directement.
    # On extrait donc game.board et game.current_player.
    elif agent_name == "minimax":
        minimax_agent = Minimax(depth=depth)
        return minimax_agent.choose_move(game.board, player=game.current_player)

    # --- Cas 3 : Alpha-Beta ---
    # best_move attend (state, depth), où 'state' est en fait l'objet game
    # lui-même (il utilise state.board, state.get_children(), etc.)
    elif agent_name == "alphabeta":
        return alpha_beta_move(game, depth=depth)

    # Ce cas ne devrait jamais arriver si LEVELS est bien rempli,
    # mais on le garde par sécurité.
    raise ValueError(f"Agent inconnu configuré pour le niveau '{level}': {agent_name}")