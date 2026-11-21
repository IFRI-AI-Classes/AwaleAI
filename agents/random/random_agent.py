import random


def random_move(game) -> int | None:
    """Choose a random legal move for the current player.

    Args:
        game: Current Game instance.

    Returns:
        int: Randomly selected hole index.
    """
    valid_moves = game.get_valid_moves()
    return random.choice(valid_moves) if valid_moves else None
