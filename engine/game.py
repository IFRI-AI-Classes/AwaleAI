from engine.board import Board
from engine.rules import Rules


class Game:
    """Awalé state, with one source of truth for moves and game endings."""

    def __init__(self, max_plies=500):
        if max_plies is not None and (type(max_plies) is not int or max_plies < 1):
            raise ValueError("max_plies doit être un entier positif ou None.")
        self.board = Board()
        self.score_p1 = 0
        self.score_p2 = 0
        self.current_player = 1
        self.plies = 0
        self.max_plies = max_plies
        self._history = {self.position_key()}
        self._repeated = False

    def position_key(self):
        return (tuple(self.board.holes), self.score_p1, self.score_p2, self.current_player)

    def copy(self):
        """Return an independent state, preserving the real game history."""
        child = object.__new__(type(self))
        child.board = self.board.copy()
        child.score_p1 = self.score_p1
        child.score_p2 = self.score_p2
        child.current_player = self.current_player
        child.plies = self.plies
        child.max_plies = self.max_plies
        child._history = self._history.copy()
        child._repeated = self._repeated
        return child

    def capture(self, last_hole):
        return Rules.capture(self.board, last_hole, self.current_player)

    def play_move(self, hole):
        """Play a legal move; invalid or post-game moves leave state intact."""
        if type(hole) is not int or self.is_game_over():
            return False
        if hole not in Rules.get_valid_moves(self.board, self.current_player):
            return False
        self._history.add(self.position_key())
        self.board, captured = Rules.simulate_move(self.board, hole, self.current_player)
        if self.current_player == 1:
            self.score_p1 += captured
        else:
            self.score_p2 += captured
        self.current_player = 3 - self.current_player
        self.plies += 1
        key = self.position_key()
        self._repeated = key in self._history
        self._history.add(key)
        return True

    def display(self):
        self.board.display()
        s1, s2 = self.final_scores()
        print(f"Score J1 : {s1}")
        print(f"Score J2 : {s2}")
        print(f"Tour joueur {self.current_player}")

    def get_valid_moves(self):
        return [] if self.is_game_over() else Rules.get_valid_moves(self.board, self.current_player)

    def get_children(self):
        children = []
        for hole in self.get_valid_moves():
            child = self.copy()
            child.play_move(hole)
            children.append(child)
        return children

    def end_reason(self):
        if self.score_p1 >= 25 or self.score_p2 >= 25:
            return "score"
        if not Rules.get_valid_moves(self.board, self.current_player):
            return "blocage"
        if self._repeated:
            return "repetition"
        if self.max_plies is not None and self.plies >= self.max_plies:
            return "limite"
        return None

    def is_game_over(self):
        return self.end_reason() is not None

    def final_scores(self):
        """Compute residual seeds on blockade, without changing the state."""
        s1, s2 = self.score_p1, self.score_p2
        if self.end_reason() == "blocage":
            remaining = sum(self.board.holes)
            if self.current_player == 1:
                s2 += remaining
            else:
                s1 += remaining
        return s1, s2

    def get_winner(self):
        if self.end_reason() in (None, "repetition", "limite"):
            return None
        s1, s2 = self.final_scores()
        return 1 if s1 > s2 else 2 if s2 > s1 else None
