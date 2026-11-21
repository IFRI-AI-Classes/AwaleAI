"""Console match using the same game endings as the API and training."""
from engine.game import Game
from agents import difficulty

NIVEAUX_DISPONIBLES = list(difficulty.LEVELS)


def demander_niveau(nom_joueur):
    while True:
        choix = input(f"Choisissez le niveau pour {nom_joueur} : ").strip().lower()
        if choix in NIVEAUX_DISPONIBLES:
            return choix
        print(f"Niveau inconnu. Choix possibles : {NIVEAUX_DISPONIBLES}")


def main():
    print("======= NIVEAUX DE JEU =======")
    for niveau in NIVEAUX_DISPONIBLES:
        print(niveau)
    levels = {1: demander_niveau("Joueur 1"), 2: demander_niveau("Joueur 2")}
    game = Game()
    while not game.is_game_over():
        game.display()
        p = game.current_player
        print(f"Joueur {p} ({levels[p]}) réfléchit...")
        hole = difficulty.choose_move(game, levels[p])
        if not game.play_move(hole):
            raise ValueError(f"L'agent a renvoyé un coup invalide : {hole}")
    game.display()
    print(f"Partie terminée : {game.end_reason()}")
    winner = game.get_winner()
    print(f"Vainqueur : Joueur {winner}" if winner else "Résultat : égalité")


if __name__ == "__main__":
    main()
