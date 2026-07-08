import copy

class Board:
    def __init__(self):
        self.holes = [4] * 12   # plus de print

    def copy(self):
        new_board = Board()
        new_board.holes = copy.deepcopy(self.holes)
        return new_board

    def display(self):
        print("\nJoueur 2")
        print(self.holes[11:5:-1])
        print(self.holes[0:6])
        print("Joueur 1\n")