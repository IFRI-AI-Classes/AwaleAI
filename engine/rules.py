class Rules:

    @staticmethod
    def is_valid_move(board, hole, player=None):
        """
        Vérifie si un coup est valide.

        Un coup est valide si :
        - l'indice existe sur le plateau ;
        - la case contient au moins une graine.

        Args:
            board: objet Board contenant le plateau.
            hole (int): indice de la case choisie.
            player (int, optional): joueur courant (1 ou 2).

        Returns:
            bool: True si le coup est valide, False sinon.
        """

        if hole < 0 or hole >= len(board.holes):
            return False

        if board.holes[hole] == 0:
            return False

        if player == 1:
            return hole in range(0, 6)

        if player == 2:
            return hole in range(6, 12)

        return True

    @staticmethod
    def sow(board, hole):
        """
        Distribue les graines de la case 'hole'.

        Args:
            board: objet Board contenant le plateau.
            hole (int): indice de la case choisie.

        Returns:
            int: indice de la dernière case où une graine a été déposée.
        """

        if not Rules.is_valid_move(board, hole):
            raise ValueError("Coup invalide.")

        seeds = board.holes[hole]

        board.holes[hole] = 0

        current = hole

        while seeds > 0:

            current = (current + 1) % len(board.holes)

            # On saute la case de départ
            if current == hole:
                continue

            board.holes[current] += 1
            seeds -= 1

        return current