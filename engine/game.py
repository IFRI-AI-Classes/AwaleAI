from engine.board import Board
from engine.rules import Rules


class Game:
    """Represent a complete Awalé game state."""

    def __init__(self):
        """Initialize a new game.

        Attributes:
            board: Game board instance.
            score_p1: Player 1 score.
            score_p2: Player 2 score.
            current_player: Active player, either 1 or 2.
        """
        self.board = Board()
        self.score_p1 = 0
        self.score_p2 = 0
        self.current_player = 1

    def capture(self, last_hole):
        """Capture seeds from the last sowed hole.

        Args:
            last_hole: Index of the last hole that received a seed.

        Returns:
            int: Number of captured seeds.
        """
        captured = 0

        if self.current_player == 1:
            opp_start, opp_end = 6, 12
        else:
            opp_start, opp_end = 0, 6

        while opp_start <= last_hole < opp_end:
            seeds = self.board.holes[last_hole]

            if seeds not in [2, 3]:
                break

            captured += seeds
            self.board.holes[last_hole] = 0
            last_hole -= 1

        return captured

    def play_move(self, hole):
        """Execute one complete move.

        Args:
            hole: Selected hole index.

        Returns:
            bool: True when the move is applied, False otherwise.
        """
        if hole not in Rules.get_valid_moves(self.board, self.current_player):
            print("Coup invalide.")
            return False

        last_hole = Rules.sow(self.board, hole)
        captured = self.capture(last_hole)

        if self.current_player == 1:
            self.score_p1 += captured
        else:
            self.score_p2 += captured

        self.current_player = 2 if self.current_player == 1 else 1
        return True

    def display(self):
        """Display the current game state."""
        self.board.display()
        print(f"Score J1 : {self.score_p1}")
        print(f"Score J2 : {self.score_p2}")
        print(f"Tour joueur {self.current_player}")

    def get_children(self) -> list:
        """Generate child game states for all legal moves.

        Returns:
            list: Child Game instances.
        """
        children = []

        for hole in range(12):
            if hole in Rules.get_valid_moves(self.board, self.current_player):
                child = Game()
                child.board = self.board.copy()
                child.score_p1 = self.score_p1
                child.score_p2 = self.score_p2
                child.current_player = self.current_player

                if child.play_move(hole):
                    children.append(child)

        return children

    def is_game_over(self) -> bool:
        """Return whether the game has ended."""
        if self.score_p1 > 24 or self.score_p2 > 24:
            return True

        if self.score_p1 == 24 and self.score_p2 == 24:
            return True

        if not Rules.get_valid_moves(self.board, self.current_player):
            return True

        return False

    def get_winner(self) -> int | None:
        """Return the winner once the game is over.

        Returns:
            int | None: Winning player number, or None for a draw.
        """
        if not Rules.get_valid_moves(self.board, self.current_player):
            remaining = sum(self.board.holes)
            if self.current_player == 1:
                self.score_p2 += remaining
            else:
                self.score_p1 += remaining
            self.board.holes = [0] * 12

        if self.score_p1 > self.score_p2:
            return 1
        elif self.score_p2 > self.score_p1:
            return 2
        else:
            return None
