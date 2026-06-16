from engine.game import Game

game = Game()

while True:

    game.display()

    raw = int(input("Choisissez une case (1-6) : "))

    # Joueur 1 : 1-6 → indices 0-5
    # Joueur 2 : 1-6 → indices 6-11
    if game.current_player == 1:
        hole = raw - 1
    else:
        hole = raw + 5  # 1→6, 2→7, 3→8, 4→9, 5→10, 6→11

    if not game.play_move(hole):
        continue