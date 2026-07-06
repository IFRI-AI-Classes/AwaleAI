from engine.game import Game
from engine.alpha_beta.elagage import best_move


game = Game()
AI_PLAYER = 1  # L'IA joue en tant que joueur 1

while True:
    game.display()

    if game.is_game_over():
        print("\n=== Partie terminée ===")
        print(f"Vainqueur : {game.get_winner()}")
        print(f"Score final — J1 : {game.score_p1} | J2 : {game.score_p2}")
        break

    if game.current_player == AI_PLAYER:
        print("L'IA réfléchit...")
        hole = best_move(game, depth=6)
        print(f"L'IA joue la case {(hole - 5) if AI_PLAYER == 2 else hole}")  # affichage 1-6
        game.play_move(hole)

    else:
        raw = int(input("Choisissez une case (1-6) : "))
        hole = raw - 1 if game.current_player == 1 else raw + 5
        if not game.play_move(hole):
            continue

