from engine.rules import Rules

class heuristic():

    def evaluate(game, player, w_diff=1.0, w_mobility=3.0, w_seeds=0.1):
        """
        Évalue la position actuelle du point de vue de 'player' (1 ou 2).
        Plus le score retourné est élevé, plus la position est favorable à 'player'.
        """
        opponent = 2 if player == 1 else 1

        if player == 1:
            diff = game.score_p1 - game.score_p2
        else:
            diff = game.score_p2 - game.score_p1

        my_mobility  = heuristic.count_valid_moves(game.board, player)   # ← fix
        opp_mobility = heuristic.count_valid_moves(game.board, opponent)  # ← fix
        mobility_score = my_mobility - opp_mobility

        opp_seeds = heuristic.seeds_in_opponent_camp(game.board, player)  # ← fix

        return (w_diff * diff) + (w_mobility * mobility_score) + (w_seeds * opp_seeds)

    def count_valid_moves(board, player):
        """Compte le nombre de coups valides pour 'player'."""
        count = 0
        for hole in range(12):
            if Rules.is_valid_move(board, hole, player):
                count += 1
        return count

    def seeds_in_opponent_camp(board, player):
        """Compte les graines présentes dans le camp adverse."""
        if player == 1:
            opponent_holes = range(6, 12)
        else:
            opponent_holes = range(0, 6)
        return sum(board.holes[h] for h in opponent_holes)