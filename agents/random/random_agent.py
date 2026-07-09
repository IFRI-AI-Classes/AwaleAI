import random
from engine.rules import Rules


def random_move(game) -> int:
    """
    Choisit un coup aléatoire parmi les coups valides du joueur courant.

    Args:
        game: instance de Game représentant l'état actuel.

    Returns:
        int: indice de la case choisie aléatoirement.
    """
    valid_moves = Rules.get_valid_moves(game.board, game.current_player)
    return random.choice(valid_moves)
