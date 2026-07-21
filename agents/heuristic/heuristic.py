from engine.rules import Rules


class heuristic:
    """Heuristic evaluation helpers for Awalé positions."""

    @staticmethod
    def evaluate(game, player, w_diff=1.0, w_mobility=3.0, w_seeds=0.1):
        """Evaluate the position from a player's perspective.

        Args:
            game: Current game state.
            player: Player number used as the evaluation reference.
            w_diff: Weight applied to score difference.
            w_mobility: Weight applied to mobility difference.
            w_seeds: Weight applied to seeds in the opponent camp.

        Returns:
            float: Higher values mean a better position for the player.
        """
        opponent = 2 if player == 1 else 1

        if player == 1:
            diff = game.score_p1 - game.score_p2
        else:
            diff = game.score_p2 - game.score_p1

        my_mobility = heuristic.count_valid_moves(game.board, player)
        opp_mobility = heuristic.count_valid_moves(game.board, opponent)
        mobility_score = my_mobility - opp_mobility

        opp_seeds = heuristic.seeds_in_opponent_camp(game.board, player)

        return (w_diff * diff) + (w_mobility * mobility_score) + (w_seeds * opp_seeds)

    @staticmethod
    def count_valid_moves(board, player):
        """Count the legal moves for a player."""
        count = 0
        for hole in range(12):
            if Rules.is_valid_move(board, hole, player):
                count += 1
        return count

    @staticmethod
    def seeds_in_opponent_camp(board, player):
        """Count seeds currently placed in the opponent camp."""
        if player == 1:
            opponent_holes = range(6, 12)
        else:
            opponent_holes = range(0, 6)
        return sum(board.holes[h] for h in opponent_holes)
