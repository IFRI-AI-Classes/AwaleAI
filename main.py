from engine.game import Game
from agents.alpha_beta.elagage import best_move as alpha_beta_move
from agents.minimax.minimax import Minimax

# Configuration des agents
MINIMAX_DEPTH    = 4

ALPHA_BETA_DEPTH = 4

minimax_agent = Minimax(depth=MINIMAX_DEPTH)

# Joueur 1 : Minimax
# Joueur 2 : Alpha-beta
AGENT_NAMES = {
    1: f"Alpha-beta  (profondeur {ALPHA_BETA_DEPTH})",
    2: f"Minimax     (profondeur {MINIMAX_DEPTH})",
}

game = Game()
AI_PLAYER = 1  # L'IA joue en tant que joueur 1
historique = set()
MAX_TOURS = 500
tour = 0

for _ in range(MAX_TOURS):
    game.display()

    # MODIF : vérification de répétition avant is_game_over().
    # L'état est un tuple (plateau, score_j1, score_j2, joueur_courant).
    tour += 1
    etat = (tuple(game.board.holes), game.score_p1, game.score_p2, game.current_player)
    if etat in historique:
        print("\n=== Nulle par répétition de position ===")
        print(f"Score final — J1 : {game.score_p1} | J2 : {game.score_p2}")
        break
    historique.add(etat)

    if game.is_game_over():
        print("\n=== Partie terminée ===")
        print(f"Score final — J1 : {game.score_p1} | J2 : {game.score_p2}")
        winner = game.get_winner()
        if winner:
            print(f"Vainqueur : Joueur {winner} — {AGENT_NAMES[winner]}")
        else:
            print("Résultat : Egalite")
        break

    if game.current_player == AI_PLAYER:
        print("L'IA réfléchit...")
        hole = alpha_beta_move(game, depth=6)
        print(f"L'IA joue la case {(hole - 5) if AI_PLAYER == 2 else hole}")  # affichage 1-6
        game.play_move(hole)

    # Joueur 2 : Minimax
    else:
        print("Minimax reflechit...")
        hole = minimax_agent.choose_move(game.board, player=2)
        print(f"Minimax joue la case {hole + 1}")
        game.play_move(hole)

else:
    # Atteint uniquement si MAX_TOURS est dépassé sans fin détectée.
    print(f"\n=== Partie interrompue après {MAX_TOURS} tours ===")
    print(f"Score final — J1 : {game.score_p1} | J2 : {game.score_p2}")