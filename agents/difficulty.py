"""Difficulty routing for AwaleAI agents."""

from typing import Optional

from agents.random.random_agent import random_move
from agents.minimax.minimax import Minimax
from agents.alpha_beta.elagage import best_move as alpha_beta_move
from awale.ai.qlearning import QLearningAgent

_qlearning_agent: Optional[QLearningAgent] = None

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
    "qlearning": {
        "agent": "qlearning",
        "depth": None,
    },
}


def _get_qlearning_agent() -> QLearningAgent:
    """Return a lazily initialized Q-learning agent instance."""
    global _qlearning_agent

    if _qlearning_agent is None:
        _qlearning_agent = QLearningAgent()

    return _qlearning_agent


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

    elif agent_name == "qlearning":
        return _get_qlearning_agent().choose_move(game, greedy=True)

    raise ValueError(f"Agent inconnu configuré pour le niveau '{level}': {agent_name}")
