import numpy as np
from engine.rules import Rules
from engine.game import Game
from agents.heuristic.heuristic import heuristic

# Considérons un objet Game qui représente l'état actuel du jeu Awélé. L'algorithme alpha-beta est utilisé pour déterminer le meilleur coup à jouer en fonction de l'état actuel du jeu et de la profondeur de recherche spécifiée.

# Anciens poids utilisés par l'évaluation manuelle ci-dessous.
# Conservés pour référence mais remplacés par heuristic.evaluate() dans evaluate_for().
W1, W2, W3, W5 = 100, 10, 5, 0.5

def evaluate(state) -> float:
    """Fonction d'évaluation pour le jeu Awélé.
    Args:
        state: l'état actuel du jeu (instance de Game).
    Returns:
        Un score numérique représentant la valeur de l'état pour le joueur maximisant.

    NOTE : cette fonction est conservée pour référence et comparaison.
    Elle est remplacée par heuristic.evaluate() dans evaluate_for(),
    qui est la fonction effectivement appelée par alpha_beta.
    """

    # Etat terminal : si un joueur a capturé plus de 24 graines, il gagne
    if state.score_p1 > 24:
        return 999999

    if state.score_p2 > 24:
        return -999999

    # Différence de graines capturées
    score = W1 * (state.score_p1 - state.score_p2)

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
    """Score relatif au joueur donné — les deux joueurs maximisent toujours.

    Remplace l'appel à evaluate() par heuristic.evaluate() qui prend
    directement un objet Game et un joueur. Les états terminaux sont
    traités ici en priorité car heuristic.evaluate() ne les gère pas.
    """

    # Etat terminal : vérification prioritaire avant tout calcul heuristique.
    # Si un joueur dépasse 24 graines capturées, la partie est gagnée.
    # On retourne une valeur absolue très grande, orientée selon le joueur.
    if state.score_p1 > 24:
        return 999999 if player == 1 else -999999
    if state.score_p2 > 24:
        return 999999 if player == 2 else -999999

    # Délégation à heuristic.evaluate() pour les positions non terminales.
    # heuristic calcule : écart de score + mobilité + graines en camp adverse.
    # Le résultat est déjà relatif à 'player', pas besoin d'inverser.
    return heuristic.evaluate(state, player)


def alpha_beta(state, depth, alpha, beta, current_player) -> int:
    """
    Implémentation de l'algorithme alpha-beta pour le jeu Awélé.
    Args:
        state: l'état actuel du jeu (instance de Game).
        depth: la profondeur maximale de recherche.
        alpha: la valeur alpha pour la coupure.
        beta: la valeur bêta pour la coupure.
        maximizing_player: booléen indiquant si c'est au tour du joueur maximisant.
    Returns:
        Le score de la meilleure action pour le joueur maximisant.
    """

    # MODIF : cas de base déplacé AVANT get_children().
    # Avant, get_children() était appelé en premier, ce qui créait des objets Game()
    # inutilement même quand depth == 0 ou la partie était terminée.
    # Résultat : des centaines de Board() instanciés → boucle infinie apparente.
    if depth == 0 or state.is_game_over():
        return evaluate_for(state, current_player)

    # get_children() uniquement si on va vraiment explorer les fils.
    children = state.get_children()

    best = -np.inf
    next_player = 2 if current_player == 1 else 1

    for child in children:
        # Negamax : on inverse le score car l'adversaire maximise aussi de son côté.
        eval = -alpha_beta(child, depth - 1, -beta, -alpha, next_player)
        best = max(best, eval)

        # MODIF : alpha = max(alpha, eval) et non min(beta, eval).
        # L'ancienne ligne était fausse : alpha doit être mis à jour
        # avec la meilleure valeur trouvée jusqu'ici, pas bridé par beta.
        # C'est ce qui permet à la coupure beta <= alpha de fonctionner correctement.
        alpha = max(alpha, eval)

        if beta <= alpha:
            break  # Coupure alpha
    return best


def best_move(state, depth=100) -> int:
    current_player = state.current_player
    next_player = 2 if current_player == 1 else 1
    best_score, best_mv = -np.inf, None

    for hole in Rules.get_valid_moves(state.board, current_player):
        # Simuler le coup dans un nouvel état enfant
        child = Game()
        child.board = state.board.copy()
        child.score_p1 = state.score_p1
        child.score_p2 = state.score_p2
        child.current_player = current_player
        child.play_move(hole)

        # On lance alpha_beta depuis l'état enfant, du point de vue de l'adversaire.
        # Le signe négatif vient du negamax : on cherche le pire pour lui = le mieux pour nous.
        s = -alpha_beta(child, depth - 1, -np.inf, np.inf, next_player)
        if s > best_score:
            best_score, best_mv = s, hole

    return best_mv