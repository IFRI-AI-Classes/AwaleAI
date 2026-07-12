import random
from engine.rules import Rules


def random_move(game) -> int:
    """Choose a random legal move for the current player.

    Args:
        game: Current Game instance.

    Returns:
        int: Randomly selected hole index.
    """
    valid_moves = Rules.get_valid_moves(game.board, game.current_player)
    return random.choice(valid_moves)
