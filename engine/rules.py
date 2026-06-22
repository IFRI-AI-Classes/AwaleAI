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
    
    @staticmethod
    def get_valid_moves(board, player):
        """
        Retourne la liste des coups valides pour le joueur courant.

        Returns:
            list: indices des cases valides.
        """

        valid_moves = []

        for hole in range(len(board.holes)):
            if Rules.is_valid_move(board, hole, player):
                valid_moves.append(hole)
        
        opponent_holes = range(0, 6) if player == 2 else range(6, 12)
        if sum(board.holes[i] for i in opponent_holes) == 0:
            # Si l'adversaire n'a plus de graines, on doit lui en donner
            nourishing_moves = []

            for hole in valid_moves:
                temp_board = board.copy()
                last_hole = Rules.sow(temp_board, hole)
                if any(temp_board.holes[i] > 0 for i in opponent_holes):
                    nourishing_moves.append(hole)
                
            if nourishing_moves:
                return nourishing_moves

        return valid_moves