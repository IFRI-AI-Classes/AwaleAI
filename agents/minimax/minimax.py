from agents.heuristic.heuristic import heuristic


class SearchState:
    def __init__(self, holes, score1, score2, player):
        self.holes  = holes
        self.score1 = score1
        self.score2 = score2
        self.player = player


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
        """
        Les cases jouables pour state.player.
        MODIF : remplace le simple check holes[h] > 0 par Rules.get_valid_moves,
        qui gère correctement la règle de nourrissage quand le camp adverse est vide.
        On fabrique un FakeBoard car Rules attend un objet avec .holes et .copy().
        """
        from engine.rules import Rules
        import copy

        class FakeBoard:
            def __init__(self, holes):
                self.holes = holes

            def copy(self):
                return FakeBoard(copy.deepcopy(self.holes))

        return Rules.get_valid_moves(FakeBoard(state.holes), state.player)

    def apply_move(self, state, hole):
        """Simule un coup complet : semis + capture. Retourne un NOUVEL état."""
        holes = state.holes[:]
        seeds = holes[hole]
        holes[hole] = 0
        current = hole
        while seeds > 0:
            current = (current + 1) % 12
            if current == hole:
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
        """Fin de partie simplifiée : le joueur courant n'a plus de coup possible."""
        return len(self.legal_moves(state)) == 0

    def evaluate(self, state, root_player):
        """
        Pont entre SearchState et heuristic.evaluate().
        heuristic attend game.score_p1, game.score_p2, game.board.holes
        → on fabrique ces objets localement.
        """
        class FakeBoard:
            def __init__(self, holes):
                self.holes = holes

        class FakeGame:
            def __init__(self, s):
                self.score_p1 = s.score1
                self.score_p2 = s.score2
                self.board    = FakeBoard(s.holes)

        return heuristic.evaluate(FakeGame(state), root_player)