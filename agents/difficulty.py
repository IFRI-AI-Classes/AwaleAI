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
    hole, _ = choose_move_by_agent(game, config["agent"], config["depth"])
    return hole


def choose_move_by_agent(game, agent: str, depth: Optional[int] = None):
    """Return the move selected by a specific agent at a given depth.

    This is the primary entry point when the caller specifies the agent and
    depth directly (e.g. from the web UI).

    Args:
        game: Current game state.
        agent: Agent identifier, one of "random", "minimax", "alphabeta",
               "qlearning".
        depth: Search depth for tree-based agents. Ignored for random and
               qlearning.

    Returns:
        tuple[int, Optional[int]]: Selected hole index and nodes explored
            (None for agents that do not count nodes).

    Raises:
        ValueError: If the agent name is unknown.
    """
    if agent not in AGENTS:
        raise ValueError(
            f"Agent inconnu : '{agent}'. "
            f"Agents disponibles : {list(AGENTS.keys())}"
        )

    depth = effective_depth(agent, depth)
    if game.is_game_over():
        return None, None

    if agent == "random":
        return random_move(game), None

    elif agent == "minimax":
        minimax_agent = Minimax(depth=depth)
        move, nodes = minimax_agent.choose_move(
            game.board,
            player=game.current_player,
            score1=game.score_p1,
            score2=game.score_p2,
            game=game,
        )
        return move, nodes

    elif agent == "alphabeta":
        move, nodes = alpha_beta_move(game, depth=depth)
        return move, nodes

    elif agent == "qlearning":
        return _get_qlearning_agent().choose_move(game, greedy=True), None

    raise ValueError(f"Agent non géré : '{agent}'")


def effective_depth(agent, depth=None):
    """Validate the supported depth and resolve defaults in one place."""
    if agent not in AGENTS:
        raise ValueError(f"Agent inconnu : '{agent}'.")
    allowed = AGENTS[agent]['depths']
    if allowed is None:
        return None
    if depth is None:
        return 2 if agent == 'minimax' else 5
    if type(depth) is not int or depth not in allowed:
        raise ValueError(f"Profondeur invalide pour {agent} : {depth}. Valeurs : {allowed}")
    return depth
