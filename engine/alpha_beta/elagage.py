import math
from ..rules import Rules
from engine.game import Game

# Considérons un objet Game qui représente l'état actuel du jeu Awélé. L'algorithme alpha-beta est utilisé pour déterminer le meilleur coup à jouer en fonction de l'état actuel du jeu et de la profondeur de recherche spécifiée.

W1, W2, W3, W5 = 100, 10, 5, 0.5
def evaluate(state) -> float:
    """Fonction d'évaluation pour le jeu Awélé.
    Args:
        state: l'état actuel du jeu (instance de Game).
    Returns:
        Un score numérique représentant la valeur de l'état pour le joueur maximisant.
    """
    remaining = 0
    p1 = state.score_p1
    p2 = state.score_p2
    # Etat terminal : si un joueur a capturé plus de 24 graines, il gagne
    
    if p1 > 24:
        return 999999

    if p2 > 24:
        return -999999
    
    if p1 == 24 and p2 == 24:
        return 0  # égalité
    
    if not Rules.get_valid_moves(state.board, state.current_player):
        remaining = sum(state.board.holes)
        if state.current_player == 1:
            p2 += remaining
        else:
            p1 += remaining

    # Différence de graines capturées
    score = W1 * (p1 - p2)

    # Opportunités de capture (cases contenant 1 ou 2 graines)
    mes_opp = sum(1 for h in state.board.holes[6:12] if h in (1, 2))
    ses_opp = sum(1 for h in state.board.holes[0:6] if h in (1, 2))

    score += W2 * (mes_opp - ses_opp)

    # Mobilité
    my_moves = Rules.get_valid_moves(state.board, 1)
    opp_moves = Rules.get_valid_moves(state.board, 2)

    score += W3 * (len(my_moves) - len(opp_moves))

    # Contrôle des graines sur le plateau
    score += W5 * (sum(state.board.holes[0:6]) - sum(state.board.holes[6:12]))

    return score

def evaluate_for(state, player) -> float:
    """Score relatif au joueur donné — les deux joueurs maximisent toujours."""
    raw = evaluate(state)
    return raw if player == 1 else -raw


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
        return evaluate_for(state, current_player)

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


def best_move(state, depth=100) -> int:
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
        child.play_move(hole)

        s = -alpha_beta(child, depth - 1, -math.inf, math.inf, next_player)
        if s > best_score:
            best_score, best_mv = s, hole

    return best_mv
