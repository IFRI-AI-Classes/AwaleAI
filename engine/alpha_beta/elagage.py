import math
from typing import Optional
from ..rules import Rules
from engine.game import Game

WIN_SCORE = 999999  # Score représentant une victoire pour le joueur maximisant
# Considérons un objet Game qui représente l'état actuel du jeu Awélé. L'algorithme alpha-beta est utilisé pour déterminer le meilleur coup à jouer en fonction de l'état actuel du jeu et de la profondeur de recherche spécifiée.

W1, W2, W3, W5 = 100, 10, 5, 0.5
def evaluate(state, player: int) -> float:
    # Camp du joueur évalué
    start = 0 if player == 1 else 6
    end = start + 6

    my_holes = state.board.holes[start:end]
    opp_holes = state.board.holes[6 - start:12 - start]

    my_score = state.score_p1 if player == 1 else state.score_p2
    opp_score = state.score_p2 if player == 1 else state.score_p1
    opponent = 2 if player == 1 else 1

    # Victoire immédiate
    if my_score > 24:
        return WIN_SCORE
    if opp_score > 24:
        return -WIN_SCORE
    if my_score == 24 and opp_score == 24:
        return 0

    # Fin de partie par blocage
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

    # Différence de graines capturées
    score += W1 * (my_score - opp_score)

    # Opportunités de capture
    my_opp = sum(1 for h in my_holes if h in (1, 2))
    opp_opp = sum(1 for h in opp_holes if h in (1, 2))
    score += W2 * (my_opp - opp_opp)

    # Mobilité
    my_moves = len(Rules.get_valid_moves(state.board, player))
    opp_moves = len(Rules.get_valid_moves(state.board, opponent))
    score += W3 * (my_moves - opp_moves)

    # Contrôle des graines sur le plateau
    score += W5 * (sum(my_holes) - sum(opp_holes))

    return score


def alpha_beta(state, depth, alpha, beta, current_player) -> float:
    """
    Implémentation de l'algorithme alpha-beta pour le jeu Awélé.
    Args:
        state: l'état actuel du jeu (instance de Game).
        depth: la profondeur maximale de recherche.
        alpha: la valeur alpha pour la coupure.
        beta: la valeur bêta pour la coupure.
    Returns:
        Le score de la meilleure action pour le joueur maximisant.
    """
    if depth == 0 or state.is_game_over():
        return evaluate(state, current_player)

    best = -math.inf
    next_player = 2 if current_player == 1 else 1


    children = state.get_children()
    for child in children:
        eval_ = -alpha_beta(child, depth - 1, -beta, -alpha, next_player)
        best = max(best, eval_)
        alpha = max(alpha, best)
        if beta <= alpha:
            break  # Coupure alpha
    return best


def best_move(state, depth=100) -> Optional[int]:
    current_player = state.current_player
    next_player = 2 if current_player == 1 else 1
    best_score, best_mv = -math.inf, None


    for hole in Rules.get_valid_moves(state.board, current_player):
        # Simuler le coup dans un nouvel état enfant
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
        
        if best_score >= WIN_SCORE:  # Si on trouve un coup gagnant, on peut s'arrêter
            break
            
    return best_mv
