import math
from typing import Optional, Tuple
from engine.rules import Rules
from engine.game import Game
from agents.heuristic.heuristic import heuristic

_nodes_counter: int = 0

WIN_SCORE = 999999

W1, W2, W3, W5 = 100, 10, 5, 0.5


def evaluate(state, player: int) -> float:
    """Evaluate a Game state from the given player's perspective."""
    start = 0 if player == 1 else 6
    end = start + 6

    my_holes = state.board.holes[start:end]
    opp_holes = state.board.holes[6 - start : 12 - start]

    my_score = state.score_p1 if player == 1 else state.score_p2
    opp_score = state.score_p2 if player == 1 else state.score_p1
    opponent = 2 if player == 1 else 1

    if my_score > 24:
        return WIN_SCORE
    if opp_score > 24:
        return -WIN_SCORE
    if my_score == 24 and opp_score == 24:
        return 0

    if not Rules.get_valid_moves(state.board, state.current_player):
        remaining = sum(state.board.holes)

        my_final = my_score
        opp_final = opp_score

        if state.current_player == player:
            opp_final += remaining
        else:
            my_final += remaining

        if my_final > opp_final:
            return WIN_SCORE
        elif opp_final > my_final:
            return -WIN_SCORE
        else:
            return 0

    score = 0

    score += W1 * (my_score - opp_score)

    my_opp = sum(1 for h in my_holes if h in (1, 2))
    opp_opp = sum(1 for h in opp_holes if h in (1, 2))
    score += W2 * (my_opp - opp_opp)

    my_moves = len(Rules.get_valid_moves(state.board, player))
    opp_moves = len(Rules.get_valid_moves(state.board, opponent))
    score += W3 * (my_moves - opp_moves)

    score += W5 * (sum(my_holes) - sum(opp_holes))

    return score


def alpha_beta(state, depth, alpha, beta, current_player) -> float:
    """Run negamax alpha-beta search for the current Awalé state.

    Args:
        state: Current Game instance (after the previous move was applied).
        depth: Remaining search depth.
        alpha: Lower bound of the search window.
        beta: Upper bound of the search window.
        current_player: The player whose turn it is at this node.  Used as
            the evaluation perspective so that the negamax sign-flip is
            consistent at every depth level.

    Returns:
        float: Score from current_player's perspective (higher = better).
    """
    global _nodes_counter
    _nodes_counter += 1

    if depth == 0 or state.is_game_over():
        return evaluate(state, current_player)

    best = -math.inf

    children = state.get_children()
    for child in children:
        # After play_move() the child already has the opponent as current_player.
        next_player = child.current_player
        eval_ = -alpha_beta(child, depth - 1, -beta, -alpha, next_player)
        best = max(best, eval_)
        alpha = max(alpha, best)
        if beta <= alpha:
            break  # Coupure alpha
    return best


def best_move(state, depth=100) -> Tuple[Optional[int], int]:
    """Return the best move and node count using alpha-beta search.

    Returns:
        tuple[Optional[int], int]: Best hole index and number of nodes explored.
    """
    global _nodes_counter
    _nodes_counter = 0

    current_player = state.current_player
    next_player = 2 if current_player == 1 else 1
    best_score, best_mv = -math.inf, None

    for hole in Rules.get_valid_moves(state.board, current_player):
        child = Game()
        child.board = state.board.copy()
        child.score_p1 = state.score_p1
        child.score_p2 = state.score_p2
        child.current_player = current_player
        if not child.play_move(hole):
            continue  # Si le coup n'est pas valide, passer au suivant

        score = -alpha_beta(child, depth - 1, -math.inf, math.inf, next_player)
        if score > best_score:
            best_score, best_mv = score, hole

        if best_score >= WIN_SCORE:
            break

    return best_mv, _nodes_counter
