"""Difficulty routing for AwaleAI agents."""

from typing import Optional

from agents.random.random_agent import random_move
from agents.minimax.minimax import Minimax
from agents.alpha_beta.elagage import best_move as alpha_beta_move
from awale.ai.qlearning import QLearningAgent

_qlearning_agent: Optional[QLearningAgent] = None

# Niveaux prédéfinis (conservés pour rétrocompatibilité CLI / main.py)
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

# Agents disponibles et leurs profondeurs min/max valides
AGENTS = {
    "random": {
        "label": "Aléatoire",
        "depths": None,          # pas de profondeur applicable
    },
    "minimax": {
        "label": "Minimax",
        "depths": list(range(1, 9)),
    },
    "alphabeta": {
        "label": "Alpha-Beta",
        "depths": list(range(1, 13)),
    },
    "qlearning": {
        "label": "Q-Learning",
        "depths": None,
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
        level: Difficulty level name (from LEVELS).

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
    return choose_move_by_agent(game, config["agent"], config["depth"])


def choose_move_by_agent(game, agent: str, depth: Optional[int] = None) -> int:
    """Return the move selected by a specific agent at a given depth.

    This is the primary entry point when the caller specifies the agent and
    depth directly (e.g. from the web UI).

    Args:
        game: Current game state.
        agent: Agent identifier — one of "random", "minimax", "alphabeta",
               "qlearning".
        depth: Search depth for tree-based agents. Ignored for random and
               qlearning.

    Returns:
        int: Selected hole index.

    Raises:
        ValueError: If the agent name is unknown.
    """
    if agent not in AGENTS:
        raise ValueError(
            f"Agent inconnu : '{agent}'. "
            f"Agents disponibles : {list(AGENTS.keys())}"
        )

    if agent == "random":
        return random_move(game)

    elif agent == "minimax":
        effective_depth = depth if depth is not None else 2
        minimax_agent = Minimax(depth=effective_depth)
        return minimax_agent.choose_move(
            game.board,
            player=game.current_player,
            score1=game.score_p1,
            score2=game.score_p2,
        )

    elif agent == "alphabeta":
        effective_depth = depth if depth is not None else 5
        return alpha_beta_move(game, depth=effective_depth)

    elif agent == "qlearning":
        return _get_qlearning_agent().choose_move(game, greedy=True)

    raise ValueError(f"Agent non géré : '{agent}'")
