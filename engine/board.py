import copy


class Board:
    """Represent the Awalé board state."""

    def __init__(self):
        self.holes = [4] * 12

    def copy(self):
        """Return a deep copy of the board.

        Returns:
            Board: Independent board instance with the same hole values.
        """
        new_board = Board()
        new_board.holes = copy.deepcopy(self.holes)
        return new_board

    def display(self):
        """Print the board in a human-readable layout."""
        print("\nJoueur 2")
        print(self.holes[11:5:-1])
        print(self.holes[0:6])
        print("Joueur 1\n")
