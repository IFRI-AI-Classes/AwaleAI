from dataclasses import dataclass

@dataclass
class SearchState:
    holes: list      # 12 cases, copie de travail
    score1: int       # score simulé du joueur 1
    score2: int       # score simulé du joueur 2
    player: int       # 1 ou 2, a qui de jouer dans cet etat


class Minimax:

    def __init__(self, depth):
        self.depth = depth

    def choose_move(self, board, player):
        state = SearchState(holes=board.holes[:], score1=0, score2=0, player=player)
        _, move = self.minimax(state, self.depth, player)
        return move

    def minimax(self, state, depth, root_player):
        if depth == 0 or self.is_terminal(state):
            return self.evaluate(state, root_player), None

        moves = self.legal_moves(state)
        maximizing = (state.player == root_player)
        best_move = moves[0]

        if maximizing:
            best_value = float('-inf')
            for move in moves:
                child = self.apply_move(state, move)
                value, _ = self.minimax(child, depth - 1, root_player)
                if value > best_value:
                    best_value, best_move = value, move
        else:
            best_value = float('inf')
            for move in moves:
                child = self.apply_move(state, move)
                value, _ = self.minimax(child, depth - 1, root_player)
                if value < best_value:
                    best_value, best_move = value, move

        return best_value, best_move

    def legal_moves(self, state):
        """Les cases jouables : le camp du joueur, non vides."""
        rng = range(0, 6) if state.player == 1 else range(6, 12)
        return [h for h in rng if state.holes[h] > 0]

    def apply_move(self, state, hole):
        """Simule un coup complet : semis + capture. Retourne un NOUVEL etat."""
        holes = state.holes[:]
        seeds = holes[hole]
        holes[hole] = 0
        current = hole
        while seeds > 0:
            current = (current + 1) % 12
            if current == hole:   # on saute la case de depart, comme Rules.sow
                continue
            holes[current] += 1
            seeds -= 1
        last_hole = current

        mover = state.player
        opp_start, opp_end = (6, 12) if mover == 1 else (0, 6)

        captured = 0
        pos = last_hole
        while opp_start <= pos < opp_end:
            s = holes[pos]
            if s not in (2, 3):
                break
            captured += s
            holes[pos] = 0
            pos -= 1

        score1, score2 = state.score1, state.score2
        if mover == 1:
            score1 += captured
        else:
            score2 += captured

        next_player = 2 if mover == 1 else 1
        return SearchState(holes=holes, score1=score1, score2=score2, player=next_player)

    def is_terminal(self, state):
        """Fin de partie simplifiee : le joueur courant n'a plus de coup possible."""
        return len(self.legal_moves(state)) == 0

    def evaluate(self, state, root_player):
        """Note du plateau du point de vue de root_player."""
        if root_player == 1:
            return state.score1 - state.score2
        else:
            return state.score2 - state.score1