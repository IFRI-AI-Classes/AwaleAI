from engine.game import Game
from engine.ai.heuristic import evaluate

game = Game()
print("Score initial (devrait être 0, plateau symétrique) :", evaluate(game, 1))
# Position neutre (déjà testée)
game_neutre = Game()
score_neutre = evaluate(game_neutre, 1)
print("Position neutre :", score_neutre)

# Position forte pour J1 : il a capturé beaucoup de graines
game_fort = Game()
game_fort.score_p1 = 20
game_fort.score_p2 = 2

score_fort = evaluate(game_fort, 1)
print("Position forte pour J1 :", score_fort)

# Vérification
if score_fort > score_neutre:
    print("✅ La position forte a un score plus élevé.")
else:
    print("❌ Problème : la position forte devrait être mieux notée.")