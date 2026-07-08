from engine.game import Game

class AwaleEnv:

    def reset(self):
        """Démarre une nouvelle partie. Retourne l'état initial."""
        self.game = Game()
        return list(self.game.board.holes)

    def state(self):
        """Retourne l'état actuel du plateau."""
        return list(self.game.board.holes)
