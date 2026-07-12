"""Difficulty routing for AwaleAI agents."""

from agents.random.random_agent import random_move
from agents.minimax.minimax import Minimax
from agents.alpha_beta.elagage import best_move as alpha_beta_move

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


def choose_move(game, level: str) -> int:
    """Return the move selected by the configured difficulty level.

    Args:
        game: Current game state.
        level: Difficulty level name.

    Returns:
        int: Selected hole index.

    Raises:
        ValueError: If the requested level is unknown.
    """
    if level not in LEVELS:
        raise ValueError(
            f"Niveau inconnu : '{level}'. "
            f"Niveaux disponibles : {list(LEVELS.keys())}"
        )

    config = LEVELS[level]
    agent_name = config["agent"]
    depth = config["depth"]

    if agent_name == "random":
        return random_move(game)

    elif agent_name == "minimax":
        minimax_agent = Minimax(depth=depth)
        return minimax_agent.choose_move(game.board, player=game.current_player)

    elif agent_name == "alphabeta":
        return alpha_beta_move(game, depth=depth)

    raise ValueError(f"Agent inconnu configuré pour le niveau '{level}': {agent_name}")
