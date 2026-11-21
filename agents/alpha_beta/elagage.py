"""Agent Alpha-Bêta : Minimax avec élagage alpha-bêta.

Cet agent est une pure optimisation de ``agents/minimax/minimax.py`` :

* même fonction d'évaluation (``agents.heuristic.heuristic.evaluate``),
  toujours calculée du point de vue du joueur racine, comme Minimax ;
* même condition d'arrêt (profondeur atteinte ou joueur courant sans coup
  légal), comme ``Minimax.is_terminal`` ;
* même formulation MAX / MIN.

Seule différence : les branches qui ne peuvent pas modifier le résultat sont
coupées (alpha >= beta). À profondeur égale, Alpha-Bêta renvoie donc la même
valeur que Minimax et un coup de même valeur (le départage des égalités peut
différer : Minimax mélange les coups, Alpha-Bêta les parcourt dans l'ordre),
en explorant moins de nœuds.
"""

import math
from typing import Optional, Tuple

from engine.rules import Rules
from engine.game import Game
from agents.heuristic.heuristic import heuristic

_nodes_counter: int = 0


def _is_terminal(state) -> bool:
    """Same terminal test as Minimax.is_terminal: no legal move left."""
    return not Rules.get_valid_moves(state.board, state.current_player)


def _child(state, hole):
    """Return a new Game obtained by playing ``hole`` from ``state``."""
    child = Game()
    child.board = state.board.copy()
    child.score_p1 = state.score_p1
    child.score_p2 = state.score_p2
    child.current_player = state.current_player
    child.play_move(hole)
    return child


def alpha_beta(state, depth, alpha, beta, root_player) -> float:
    """Run minimax search with alpha-beta pruning.

    Args:
        state: Current Game instance.
        depth: Remaining search depth.
        alpha: Best value already guaranteed to MAX (root player).
        beta: Best value already guaranteed to MIN (opponent).
        root_player: Player whose perspective is maximized (same role as
            ``root_player`` in Minimax.minimax).

    Returns:
        float: Heuristic value of the state from root_player's perspective.
    """
    global _nodes_counter
    _nodes_counter += 1

    if depth == 0 or _is_terminal(state):
        return heuristic.evaluate(state, root_player)

    moves = Rules.get_valid_moves(state.board, state.current_player)

    if state.current_player == root_player:
        value = -math.inf
        for hole in moves:
            value = max(value, alpha_beta(_child(state, hole), depth - 1, alpha, beta, root_player))
            alpha = max(alpha, value)
            if alpha >= beta:
                break  # Coupure bêta
        return value

    value = math.inf
    for hole in moves:
        value = min(value, alpha_beta(_child(state, hole), depth - 1, alpha, beta, root_player))
        beta = min(beta, value)
        if alpha >= beta:
            break  # Coupure alpha
    return value


def best_move(state, depth=100) -> Tuple[Optional[int], int]:
    """Return the best move and node count using alpha-beta search.

    Returns:
        tuple[Optional[int], int]: Best hole index and number of nodes explored.
    """
    global _nodes_counter
    _nodes_counter = 1  # nœud racine (compté comme dans Minimax)

    root_player = state.current_player
    best_score, best_mv = -math.inf, None
    alpha = -math.inf

    for hole in Rules.get_valid_moves(state.board, root_player):
        score = alpha_beta(_child(state, hole), depth - 1, alpha, math.inf, root_player)
        if score > best_score:
            best_score, best_mv = score, hole
        alpha = max(alpha, best_score)

    return best_mv, _nodes_counter
