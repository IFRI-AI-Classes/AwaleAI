"""Minimax using the same transitions and endings as the game engine."""
import random

from engine.game import Game
from agents.heuristic.heuristic import heuristic


class SearchState(Game):
    """Compatibility adapter for callers constructing a search position."""

    def __init__(self, holes, score1, score2, player):
        super().__init__()
        self.board.holes = holes[:]
        self.score_p1, self.score_p2 = score1, score2
        self.current_player = player
        self._history = {self.position_key()}

    holes = property(lambda s: s.board.holes)
    score1 = property(lambda s: s.score_p1)
    score2 = property(lambda s: s.score_p2)
    player = property(lambda s: s.current_player)


class Minimax:
    def __init__(self, depth):
        if type(depth) is not int or depth < 1:
            raise ValueError("La profondeur doit être un entier positif.")
        self.depth = depth
        self._nodes = 0

    def choose_move(self, board, player, score1=0, score2=0, *, game=None):
        if type(player) is not int or player not in (1, 2):
            raise ValueError("player doit être 1 ou 2.")
        if game is not None and player != game.current_player:
            raise ValueError("player doit correspondre au joueur actif de game.")
        self._nodes = 0
        state = game.copy() if game is not None else SearchState(board.holes, score1, score2, player)
        _, move = self.minimax(state, self.depth, player)
        return move, self._nodes

    def _shuffled_moves(self, moves):
        moves = list(moves)
        random.shuffle(moves)
        return moves

    def minimax(self, state, depth, root_player):
        self._nodes += 1
        if depth <= 0 or self.is_terminal(state):
            return self.evaluate(state, root_player), None
        maximizing = state.current_player == root_player
        best_value = float("-inf") if maximizing else float("inf")
        best_move = None
        for move in self._shuffled_moves(self.legal_moves(state)):
            child = self.apply_move(state, move)
            value, _ = self.minimax(child, depth - 1, root_player)
            immediate_win = (value == best_value and child.is_game_over()
                             and child.get_winner() == state.current_player)
            if (maximizing and value > best_value) or (not maximizing and value < best_value) or immediate_win:
                best_value, best_move = value, move
        return best_value, best_move

    def legal_moves(self, state):
        return state.get_valid_moves()

    def apply_move(self, state, hole):
        child = state.copy()
        if not child.play_move(hole):
            raise ValueError(f"Coup invalide : {hole}")
        return child

    def is_terminal(self, state):
        return state.is_game_over()

    def evaluate(self, state, root_player):
        return heuristic.evaluate(state, root_player)
