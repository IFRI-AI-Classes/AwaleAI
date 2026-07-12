from engine.game import Game
from agents import difficulty

NIVEAUX_DISPONIBLES = ["facile", "moyen", "difficile", "expert"]

print("=======NIVEAUX DE JEU=======")
for niveau in NIVEAUX_DISPONIBLES:
    print(niveau)


def demander_niveau(nom_joueur: str) -> str:
    """Prompt for a valid difficulty level.

    Args:
        nom_joueur: Display name of the player being configured.

    Returns:
        str: A validated difficulty level.
    """
    while True:
        choix = input(f"Choisissez le niveau pour {nom_joueur} : ").strip().lower()
        if choix in NIVEAUX_DISPONIBLES:
            return choix
        print(f"Niveau inconnu. Choix possibles : {NIVEAUX_DISPONIBLES}")


level_p1 = demander_niveau("Joueur 1")
level_p2 = demander_niveau("Joueur 2")

AGENT_NAMES = {
    1: f"Joueur 1 ({level_p1})",
    2: f"Joueur 2 ({level_p2})",
}

game = Game()
historique = set()
MAX_TOURS = 500
tour = 0

for _ in range(MAX_TOURS):
    game.display()

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

    level_courant = level_p1 if game.current_player == 1 else level_p2

    print(f"{AGENT_NAMES[game.current_player]} réfléchit...")
    hole = difficulty.choose_move(game, level_courant)
    print(f"{AGENT_NAMES[game.current_player]} joue la case {hole}")
    game.play_move(hole)

else:
    print(f"\n=== Partie interrompue après {MAX_TOURS} tours ===")
    print(f"Score final — J1 : {game.score_p1} | J2 : {game.score_p2}")
