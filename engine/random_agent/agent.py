import random

class RandomAgent:
    """
    Agent qui choisit un coup aléatoire parmi les coups valides.
    """
    def __init__(self, player):
        """
        Args:
            player (int): Le numéro du joueur (1 ou 2) que cet agent représente.
        """
        if type(player) is not int or player not in (1, 2):
            raise ValueError("player doit être 1 ou 2.")
        self.player = player

    def choose_move(self, game):
        if game.is_game_over():
            return None
        if self.player != game.current_player:
            raise ValueError("Ce n'est pas le tour de cet agent.")
        valid_moves = game.get_valid_moves()
        return random.choice(valid_moves) if valid_moves else None
