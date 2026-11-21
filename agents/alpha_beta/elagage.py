"""Minimax with alpha-beta pruning and a fixed root-player perspective."""
import math

from agents.heuristic.heuristic import WIN_SCORE, heuristic


def evaluate(state, player):
    return heuristic.evaluate(state, player)


class _Search:
    def __init__(self):
        self.nodes = 0

    def run(self, state, depth, alpha, beta, root_player):
        self.nodes += 1
        if depth <= 0 or state.is_game_over():
            return evaluate(state, root_player)
        maximizing = state.current_player == root_player
        value = -math.inf if maximizing else math.inf
        for hole in state.get_valid_moves():
            child = state.copy()
            child.play_move(hole)
            score = self.run(child, depth - 1, alpha, beta, root_player)
            if maximizing:
                value = max(value, score)
                alpha = max(alpha, value)
            else:
                value = min(value, score)
                beta = min(beta, value)
            if alpha >= beta:
                break
        return value


def alpha_beta(state, depth, alpha, beta, root_player):
    """Return the value for root_player, including real terminal outcomes."""
    return _Search().run(state, depth, alpha, beta, root_player)


def best_move(state, depth=5):
    """Return (move, nodes), with counters isolated for each search."""
    if type(depth) is not int or depth < 1:
        raise ValueError("La profondeur doit être un entier positif.")
    search = _Search()
    search.nodes = 1
    if state.is_game_over():
        return None, search.nodes
    root_player = state.current_player
    best_score, best_mv, alpha = -math.inf, None, -math.inf
    for hole in state.get_valid_moves():
        child = state.copy()
        child.play_move(hole)
        score = search.run(child, depth - 1, alpha, math.inf, root_player)
        immediate_win = (score == best_score and child.is_game_over()
                         and child.get_winner() == root_player)
        if score > best_score or immediate_win:
            best_score, best_mv = score, hole
        alpha = max(alpha, best_score)
    return best_mv, search.nodes
