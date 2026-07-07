import random
from ..rules import Rules

class RandomAgent:
    """
    Agent qui choisit un coup aléatoire parmi les coups valides.
    """
    def __init__(self, player):
        """
        Args:
            player (int): Le numéro du joueur (1 ou 2) que cet agent représente.
        """
        self.player = player

    def choose_move(self, game):
        valid_moves = [hole for hole in range(12) if hole in Rules.get_valid_moves(game.board, self.player)]
        return random.choice(valid_moves) if valid_moves else None