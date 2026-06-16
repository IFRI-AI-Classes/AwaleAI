from engine.board import Board
from engine.rules import Rules


class Game:
    """
    Cette classe gère :
    - le plateau de jeu ;
    - les scores des joueurs ;
    - le joueur courant ;
    - les captures ;
    - le déroulement des tours.
    """

    def __init__(self):
        """
        Initialise une nouvelle partie.

        Attributs :
            board (Board): plateau de jeu.
            score_p1 (int): score du joueur 1.
            score_p2 (int): score du joueur 2.
            current_player (int): joueur dont c'est le tour (1 ou 2).
        """

        self.board = Board()

        self.score_p1 = 0
        self.score_p2 = 0

        self.current_player = 1

    def capture(self, last_hole):
        """
        Capture les graines à partir de la dernière case jouée.

        Une capture est effectuée lorsque la case contient
        exactement 2 ou 3 graines.

        La capture continue vers les cases précédentes tant
        que celles-ci contiennent également 2 ou 3 graines.

        Args:
            last_hole (int): indice de la dernière case
                             où une graine a été déposée.

        Returns:
            int: nombre total de graines capturées.
        """

        captured = 0

        while last_hole >= 0:

            seeds = self.board.holes[last_hole]

            # Arrêt si la case ne contient ni 2 ni 3 graines
            if seeds not in [2, 3]:
                break

            # Ajout des graines capturées
            captured += seeds

            # Vidage de la case capturée
            self.board.holes[last_hole] = 0

            # Passage à la case précédente
            last_hole -= 1

        return captured

    def play_move(self, hole):
        """
        Exécute un coup complet.

        Étapes :
        1. Distribuer les graines.
        2. Vérifier les captures.
        3. Mettre à jour le score.
        4. Passer au joueur suivant.

        Args:
            hole (int): case choisie par le joueur.
        """

        if not Rules.is_valid_move(
                self.board,
                hole,
                self.current_player):

            print("Coup invalide.")
            return False

        last_hole = Rules.sow(self.board, hole)

        captured = self.capture(last_hole)

        if self.current_player == 1:
            self.score_p1 += captured
        else:
            self.score_p2 += captured

        self.current_player = 2 if self.current_player == 1 else 1

        return True

    def display(self):
        """
        Affiche l'état actuel de la partie.

        Affiche :
        - le plateau ;
        - les scores ;
        - le joueur dont c'est le tour.
        """

        self.board.display()

        print(f"Score J1 : {self.score_p1}")
        print(f"Score J2 : {self.score_p2}")

        print(f"Tour joueur {self.current_player}")