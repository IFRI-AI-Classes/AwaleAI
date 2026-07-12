from engine.game import Game


class AwaleEnv:
    """Minimal environment wrapper around Game."""

    def reset(self):
        """Start a new game.

        Returns:
            list: Initial board state.
        """
        self.game = Game()
        return list(self.game.board.holes)

    def state(self):
        """Return the current board state.

        Returns:
            list: Current board state.
        """
        return list(self.game.board.holes)
