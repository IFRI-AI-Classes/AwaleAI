from agents.heuristic.heuristic import heuristic


class SearchState:
    """Lightweight immutable search state used by Minimax."""

    def __init__(self, holes, score1, score2, player):
        self.holes = holes
        self.score1 = score1
        self.score2 = score2
        self.player = player


class Minimax:
    """Minimax agent backed by the heuristic evaluator."""

    def __init__(self, depth):
        """Initialize the search depth.

        Args:
            depth: Maximum search depth.
        """
        self.depth = depth

    def choose_move(self, board, player):
        """Choose the best move for the current position.

        Args:
            board: Current board state.
            player: Current player number.

        Returns:
            int: Selected hole index.
        """
        state = SearchState(holes=board.holes[:], score1=0, score2=0, player=player)
        _, move = self.minimax(state, self.depth, player)
        return move

    def minimax(self, state, depth, root_player):
        """Run the minimax search from a given state.

        Args:
            state: Current search state.
            depth: Remaining search depth.
            root_player: Player whose perspective is maximized.

        Returns:
            tuple: Best score and associated move.
        """
        if depth == 0 or self.is_terminal(state):
            return self.evaluate(state, root_player), None

        moves = self.legal_moves(state)
        maximizing = state.player == root_player
        best_move = moves[0]

        if maximizing:
            best_value = float("-inf")
            for move in moves:
                child = self.apply_move(state, move)
                value, _ = self.minimax(child, depth - 1, root_player)
                if value > best_value:
                    best_value, best_move = value, move
        else:
            best_value = float("inf")
            for move in moves:
                child = self.apply_move(state, move)
                value, _ = self.minimax(child, depth - 1, root_player)
                if value < best_value:
                    best_value, best_move = value, move

        return best_value, best_move

    def legal_moves(self, state):
        """Return legal moves for the given search state.

        Args:
            state: Current search state.

        Returns:
            list: Legal move indices.
        """
        from engine.rules import Rules
        import copy

        class FakeBoard:
            def __init__(self, holes):
                self.holes = holes

            def copy(self):
                return FakeBoard(copy.deepcopy(self.holes))

        return Rules.get_valid_moves(FakeBoard(state.holes), state.player)

    def apply_move(self, state, hole):
        """Simulate a complete move and return the next search state."""
        holes = state.holes[:]
        seeds = holes[hole]
        holes[hole] = 0
        current = hole
        while seeds > 0:
            current = (current + 1) % 12
            if current == hole:
                continue
            holes[current] += 1
            seeds -= 1
        last_hole = current

        mover = state.player
        opp_start, opp_end = (6, 12) if mover == 1 else (0, 6)

        captured = 0
        pos = last_hole
        while opp_start <= pos < opp_end:
            s = holes[pos]
            if s not in (2, 3):
                break
            captured += s
            holes[pos] = 0
            pos -= 1

        score1, score2 = state.score1, state.score2
        if mover == 1:
            score1 += captured
        else:
            score2 += captured

        next_player = 2 if mover == 1 else 1
        return SearchState(
            holes=holes, score1=score1, score2=score2, player=next_player
        )

    def is_terminal(self, state):
        """Return whether the search state is terminal."""
        return len(self.legal_moves(state)) == 0

    def evaluate(self, state, root_player):
        """Evaluate a search state with the heuristic module.

        Args:
            state: Current search state.
            root_player: Player used as the evaluation reference.

        Returns:
            float: Heuristic score for the state.
        """

        class FakeBoard:
            def __init__(self, holes):
                self.holes = holes

        class FakeGame:
            def __init__(self, s):
                self.score_p1 = s.score1
                self.score_p2 = s.score2
                self.board = FakeBoard(s.holes)

        return heuristic.evaluate(FakeGame(state), root_player)
