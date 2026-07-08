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

        # définir la zone adverse
        if self.current_player == 1:
            opp_start, opp_end = 6, 12
        else:
            opp_start, opp_end = 0, 6

        # on recule tant qu'on est dans le camp adverse
        while opp_start <= last_hole < opp_end:
            seeds = self.board.holes[last_hole]

            if seeds not in [2, 3]:
                break

            captured += seeds
            self.board.holes[last_hole] = 0
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
        if hole not in Rules.get_valid_moves(self.board, self.current_player):
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

    def get_children(self) -> list:
        """
        Génère les états enfants du jeu actuel.

        Un état enfant correspond à un coup valide joué par le joueur courant.

        Returns:
            list: liste des états enfants (objets Game).
        """
        children = []

        for hole in range(12):
            if hole in Rules.get_valid_moves(self.board, self.current_player):
                child = Game()
                child.board = self.board.copy()
                child.score_p1 = self.score_p1
                child.score_p2 = self.score_p2
                child.current_player = self.current_player

                if child.play_move(hole) :
                    children.append(child)

        return children

    def is_game_over(self) -> bool:
        """
        La partie est terminée si :
        - Le joueur courant n'a plus de coups légaux (sa rangée est vide).
        - Un joueur a déjà capturé plus de 24 graines (majorité absolue).
        - Égalité à 24-24 (match nul).
        """
        if self.score_p1 > 24 or self.score_p2 > 24:
            return True

        if self.score_p1 == 24 and self.score_p2 == 24:
            return True

        if not Rules.get_valid_moves(self.board, self.current_player):
            return True

        return False

    def get_winner(self) -> int | None:
        """
        Appelée uniquement si is_game_over() == True.
        Si le joueur courant est bloqué, les graines restantes
        vont à l'autre joueur (règle Awalé classique).

        MODIF : retourne un int (1, 2) ou None pour l'égalité,
        au lieu d'une chaîne. Permet à main.py d'utiliser
        directement AGENT_NAMES[winner] sans conversion.
        """
        if not Rules.get_valid_moves(self.board, self.current_player):
            remaining = sum(self.board.holes)
            if self.current_player == 1:
                self.score_p2 += remaining
            else:
                self.score_p1 += remaining
            self.board.holes = [0] * 12

        if self.score_p1 > self.score_p2:
            return 1
        elif self.score_p2 > self.score_p1:
            return 2
        else:
            return None