class Board:
    def __init__(self):
        self.holes = [4] * 12
        print(self.holes)

    def display(self):
        print("\nJoueur 2")
        print(self.holes[11:5:-1])
        print(self.holes[0:6])
        print("Joueur 1\n")
  
  
# Tester la classe    
board = Board()
board.display()