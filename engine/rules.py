class Rules:
    """Static helpers that implement Awalé move rules."""

    @staticmethod
    def is_valid_move(board, hole, player=None):
        """Check whether a move is legal.

        Args:
            board: Board instance containing the current holes.
            hole: Selected hole index.
            player: Optional current player (1 or 2).

        Returns:
            bool: True if the move is legal, False otherwise.
        """

        if hole < 0 or hole >= len(board.holes):
            return False

        if board.holes[hole] == 0:
            return False

        if player == 1:
            return hole in range(0, 6)

        if player == 2:
            return hole in range(6, 12)

        return True

    @staticmethod
    def sow(board, hole):
        """Sow seeds from a selected hole in anti-clockwise order.

        Internal index convention
        -------------------------
        Player 1 owns holes[0..5]  — displayed left → right  (bottom row).
        Player 2 owns holes[6..11] — displayed right → left  (top row).

        Anti-clockwise traversal = incrementing index modulo 12:
          0 → 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 0 → …

        When seeds > 11 the starting hole is skipped on the first pass
        (Kroo rule): ``if current == hole: continue``.

        Args:
            board: Board instance containing the current holes.
            hole: Selected hole index.

        Returns:
            int: Index of the last hole that received a seed.
        """

        if not Rules.is_valid_move(board, hole):
            raise ValueError("Coup invalide.")

        seeds = board.holes[hole]

        board.holes[hole] = 0

        current = hole

        while seeds > 0:
            current = (current + 1) % len(board.holes)

            if current == hole:
                continue

            board.holes[current] += 1
            seeds -= 1

        return current

    @staticmethod
    def get_valid_moves(board, player):
        """Return the legal moves for the given player.

        Args:
            board: Board instance containing the current holes.
            player: Player number.

        Returns:
            list: Indices of legal holes.
        """

        valid_moves = []

        for hole in range(len(board.holes)):
            if Rules.is_valid_move(board, hole, player):
                valid_moves.append(hole)

        opponent_holes = range(0, 6) if player == 2 else range(6, 12)
        if sum(board.holes[i] for i in opponent_holes) == 0:
            nourishing_moves = []

            for hole in valid_moves:
                temp_board = board.copy()
                last_hole = Rules.sow(temp_board, hole)
                if any(temp_board.holes[i] > 0 for i in opponent_holes):
                    nourishing_moves.append(hole)

            if nourishing_moves:
                return nourishing_moves

        return valid_moves
