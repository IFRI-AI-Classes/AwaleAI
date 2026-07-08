from engine.game import Game
from agents.alpha_beta.elagage import best_move as alpha_beta_move
from agents.minimax.minimax import Minimax

# Configuration des agents
MINIMAX_DEPTH    = 7

ALPHA_BETA_DEPTH = 7

minimax_agent = Minimax(depth=MINIMAX_DEPTH)

# Joueur 1 : Minimax
# Joueur 2 : Alpha-beta
AGENT_NAMES = {
    1: f"Alpha-beta  (profondeur {ALPHA_BETA_DEPTH})",
    2: f"Minimax     (profondeur {MINIMAX_DEPTH})",
}

game = Game()

# MODIF : détection de répétition de position.
# Sans ce mécanisme, les deux agents peuvent tourner en boucle
# sur le même état indéfiniment quand aucun n'arrive à capturer.
# On stocke chaque état vu ; si le même réapparaît → nulle.
historique = set()
MAX_TOURS  = 300   # filet de sécurité absolu

print("=== AwaleAI — Minimax vs Alpha-beta ===")
print(f"  J1 : {AGENT_NAMES[1]}")
print(f"  J2 : {AGENT_NAMES[2]}")
print("=" * 40)

for tour in range(MAX_TOURS):
    game.display()

    # MODIF : vérification de répétition avant is_game_over().
    # L'état est un tuple (plateau, score_j1, score_j2, joueur_courant).
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

    current = game.current_player
    print(f"\nTour du Joueur {current} — {AGENT_NAMES[current]}")

    # Joueur 1 : Alpha-beta
    if current == 1:
        print("Alpha-beta reflechit...")
        hole = alpha_beta_move(game, depth=ALPHA_BETA_DEPTH)
        print(f"Alpha-beta joue la case {hole + 1}")   # ou adapte selon l'indexation
        game.play_move(hole)

    # Joueur 2 : Minimax
    else:
        print("Minimax reflechit...")
        hole = minimax_agent.choose_move(game.board, player=2)
        print(f"Minimax joue la case {hole + 1}")
        game.play_move(hole)

else:
    # MODIF : atteint uniquement si MAX_TOURS est dépassé sans fin détectée.
    print(f"\n=== Partie interrompue après {MAX_TOURS} tours ===")
    print(f"Score final — J1 : {game.score_p1} | J2 : {game.score_p2}")