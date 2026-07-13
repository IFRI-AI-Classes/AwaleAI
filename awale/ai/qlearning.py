"""Persistent Q-learning agent for Awalé."""

from __future__ import annotations

import json
import math
import os
import random
import time
from typing import Dict, List, Optional, Tuple

from engine.game import Game
from engine.rules import Rules
from agents.random.random_agent import random_move
from agents.alpha_beta.elagage import best_move as alpha_beta_move

_BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "models")
PATH_LATEST = os.path.join(_BASE_DIR, "q_table_latest.json")
PATH_BEST = os.path.join(_BASE_DIR, "q_table_best.json")

ALPHA = 0.15  # Taux d'apprentissage
GAMMA = 0.95  # Facteur d'actualisation
EPSILON_START = 1.00  # Epsilon initial
EPSILON_MIN = 0.05  # Epsilon plancher
SAVE_EVERY = 100  # Sauvegarde toutes les N parties

R_WIN = 100.0
R_LOSS = -100.0
R_DRAW = 0.0
R_CAPTURE = 2.0
R_OPP_CAP = -2.0
R_TIME = -0.5


def encode_state(game: Game) -> str:
    """
    Encode l'état du jeu du point de vue du *joueur courant*.

    Format : "mes_trous|trous_adversaire|score_moi|score_lui"
    où mes_trous / trous_adversaire sont les 6 cases de chaque camp.

    Grâce à cette symétrie, la même Q-Table fonctionne pour J1 et J2.
    """
    p = game.current_player
    if p == 1:
        my_holes = game.board.holes[0:6]
        opp_holes = game.board.holes[6:12]
        my_score = game.score_p1
        opp_score = game.score_p2
    else:
        my_holes = game.board.holes[6:12]
        opp_holes = game.board.holes[0:6]
        my_score = game.score_p2
        opp_score = game.score_p1

    return (
        ",".join(str(h) for h in my_holes)
        + "|"
        + ",".join(str(h) for h in opp_holes)
        + "|"
        + str(my_score)
        + "|"
        + str(opp_score)
    )


def encode_action(game: Game, hole: int) -> int:
    """
    Convertit un indice absolu (0-11) en indice relatif (0-5)
    du point de vue du joueur courant.
    """
    return hole if game.current_player == 1 else hole - 6


def decode_action(game: Game, relative_action: int) -> int:
    """
    Convertit un indice relatif (0-5) en indice absolu (0-11)
    selon le joueur courant.
    """
    return relative_action if game.current_player == 1 else relative_action + 6


class QLearningAgent:
    """Persistent Q-learning agent with symmetric state encoding."""

    def __init__(
        self,
        alpha: float = ALPHA,
        gamma: float = GAMMA,
        epsilon: float = EPSILON_START,
        epsilon_min: float = EPSILON_MIN,
    ) -> None:
        self.alpha = alpha
        self.gamma = gamma
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min

        self.q_table: Dict[str, Dict[str, float]] = {}
        self.total_episodes: int = 0
        self.best_win_rate: float = 0.0
        self._epsilon_decay: float = 0.0

        self.load()

    def _get_q(self, state: str, action: int) -> float:
        """Return Q(s, a) with lazy initialization."""
        return self.q_table.get(state, {}).get(str(action), 0.0)

    def _set_q(self, state: str, action: int, value: float) -> None:
        """Set Q(s, a), creating the state entry if needed."""
        if state not in self.q_table:
            self.q_table[state] = {}
        self.q_table[state][str(action)] = value

    def _max_q(self, state: str, valid_actions: List[int]) -> float:
        """Return max_a Q(s, a) over valid actions."""
        if not valid_actions:
            return 0.0
        return max(self._get_q(state, a) for a in valid_actions)

    def choose_move(self, game: Game, greedy: bool = False) -> int:
        """
        Choose an absolute move index via epsilon-greedy.

        Args:
            game: Current game state.
            greedy: Force pure exploitation when True.

        Returns:
            int: Selected absolute hole index.
        """
        valid_abs = Rules.get_valid_moves(game.board, game.current_player)
        if not valid_abs:
            raise ValueError("Aucun coup valide disponible.")

        if not greedy and random.random() < self.epsilon:
            return random.choice(valid_abs)

        state = encode_state(game)
        best_rel, best_val = None, -math.inf
        for hole in valid_abs:
            rel = encode_action(game, hole)
            val = self._get_q(state, rel)
            if val > best_val:
                best_val, best_rel = val, rel

        if best_rel is None:
            return random.choice(valid_abs)
        return decode_action(game, best_rel)

    def update(
        self,
        state: str,
        action_rel: int,
        reward: float,
        next_state: str,
        next_valid_actions: List[int],
        done: bool,
    ) -> None:
        """Apply the Bellman update to Q(s, a)."""
        q_current = self._get_q(state, action_rel)
        target = reward
        if not done:
            target += self.gamma * self._max_q(next_state, next_valid_actions)
        self._set_q(state, action_rel, q_current + self.alpha * (target - q_current))

    def set_epsilon_decay(self, n_episodes: int, start: Optional[float] = None) -> None:
        """Configure the linear epsilon decay over a fixed number of episodes."""
        if start is not None:
            self.epsilon = min(1.0, max(self.epsilon_min, start))
        span = max(self.epsilon - self.epsilon_min, 0.0)
        self._epsilon_decay = span / max(n_episodes, 1)

    def decay_epsilon(self) -> None:
        """Apply one linear epsilon decay step."""
        self.epsilon = max(self.epsilon_min, self.epsilon - self._epsilon_decay)

    def _ensure_models_dir(self) -> None:
        os.makedirs(os.path.normpath(_BASE_DIR), exist_ok=True)

    def save(self, path: str) -> None:
        """Save the Q-table and metadata to JSON atomically."""
        self._ensure_models_dir()
        payload = {
            "epsilon": self.epsilon,
            "total_episodes": self.total_episodes,
            "best_win_rate": self.best_win_rate,
            "q_table": self.q_table,
        }
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, separators=(",", ":"))
        os.replace(tmp, path)

    def load(self) -> None:
        """Load the persisted Q-table, preferring the best checkpoint first."""
        for path in [PATH_BEST, PATH_LATEST]:
            norm = os.path.normpath(path)
            if os.path.isfile(norm):
                try:
                    with open(norm, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    self.q_table = data.get("q_table", {})
                    self.epsilon = float(data.get("epsilon", EPSILON_START))
                    self.total_episodes = int(data.get("total_episodes", 0))
                    self.best_win_rate = float(data.get("best_win_rate", 0.0))
                    print(
                        f"[QLearning] Chargé depuis {os.path.basename(norm)} "
                        f"| {len(self.q_table)} états | "
                        f"ε={self.epsilon:.3f} | épisodes={self.total_episodes}"
                    )
                    return
                except (json.JSONDecodeError, KeyError) as exc:
                    print(f"[QLearning] Erreur lecture {norm}: {exc}")
        print("[QLearning] Démarrage avec une Q-Table vide.")

    def save_latest(self) -> None:
        """Save the latest checkpoint."""
        self.save(os.path.normpath(PATH_LATEST))

    def save_best(self) -> None:
        """Save the best checkpoint."""
        self.save(os.path.normpath(PATH_BEST))


def _opp_captures_after(game: Game, opp_move_fn) -> int:
    """Estimate how many seeds the opponent would capture after a reply."""
    sim = Game()
    sim.board = game.board.copy()
    sim.score_p1 = game.score_p1
    sim.score_p2 = game.score_p2
    sim.current_player = game.current_player  # c'est déjà l'adversaire

    opp = sim.current_player
    score_before = sim.score_p1 if opp == 1 else sim.score_p2

    try:
        move = opp_move_fn(sim)
        sim.play_move(move)
    except Exception:
        return 0

    score_after = sim.score_p1 if opp == 1 else sim.score_p2
    return max(0, score_after - score_before)


def run_episode(
    agent: QLearningAgent,
    opp_move_fn,
    agent_player: int,
    update_agent: bool = True,
) -> Tuple[Optional[int], float]:
    """
    Joue une partie complète : agent vs adversaire.

    Returns
    -------
    (winner, total_reward_agent)
    winner = 1, 2 ou None (égalité).
    """
    game = Game()
    total_reward = 0.0
    transitions: List[Tuple[str, int, float, str]] = []
    MAX_TURNS = 500

    for _ in range(MAX_TURNS):
        if game.is_game_over():
            break

        if game.current_player == agent_player:
            state = encode_state(game)
            s_before = game.score_p1 if agent_player == 1 else game.score_p2

            hole = agent.choose_move(game, greedy=(not update_agent))
            action_rel = encode_action(game, hole)
            game.play_move(hole)

            s_after = game.score_p1 if agent_player == 1 else game.score_p2
            my_cap = s_after - s_before

            step_r = R_TIME + R_CAPTURE * my_cap

            if not game.is_game_over() and game.current_player != agent_player:
                opp_cap = _opp_captures_after(game, opp_move_fn)
                step_r += R_OPP_CAP * opp_cap

            next_state = encode_state(game) if not game.is_game_over() else ""
            transitions.append((state, action_rel, step_r, next_state))
            total_reward += step_r

        else:
            try:
                opp_hole = opp_move_fn(game)
                game.play_move(opp_hole)
            except Exception:
                break

    winner = game.get_winner()
    terminal_r = (
        R_WIN if winner == agent_player else R_DRAW if winner is None else R_LOSS
    )
    total_reward += terminal_r

    if update_agent and transitions:
        for i, (s, a, r, ns) in enumerate(transitions):
            done = i == len(transitions) - 1
            tr = terminal_r if done else 0.0
            if done:
                agent.update(s, a, r + tr, "", [], done=True)
            else:
                ns_next = transitions[i + 1][0]
                # actions valides dans ns ne sont pas stockées ici,
                # on utilise la Q-valeur brute du prochain état choisi
                next_rel = transitions[i + 1][1]
                nq = agent._get_q(ns, next_rel)
                target = r + agent.gamma * nq
                curr_q = agent._get_q(s, a)
                agent._set_q(s, a, curr_q + agent.alpha * (target - curr_q))

    return winner, total_reward


def run_selfplay_episode(agent: QLearningAgent) -> Tuple[Optional[int], float, float]:
    """Run one self-play episode and update the shared Q-table."""
    game = Game()
    MAX_TURNS = 500
    trans_p1: List[Tuple[str, int, float]] = []
    trans_p2: List[Tuple[str, int, float]] = []
    r1 = r2 = 0.0

    for _ in range(MAX_TURNS):
        if game.is_game_over():
            break

        p = game.current_player
        state = encode_state(game)
        sb = game.score_p1 if p == 1 else game.score_p2

        hole = agent.choose_move(game, greedy=False)
        rel = encode_action(game, hole)
        game.play_move(hole)

        sa = game.score_p1 if p == 1 else game.score_p2
        step_r = R_TIME + R_CAPTURE * (sa - sb)

        if p == 1:
            trans_p1.append((state, rel, step_r))
            r1 += step_r
        else:
            trans_p2.append((state, rel, step_r))
            r2 += step_r

    winner = game.get_winner()
    term1 = R_WIN if winner == 1 else (R_DRAW if winner is None else R_LOSS)
    term2 = R_WIN if winner == 2 else (R_DRAW if winner is None else R_LOSS)
    r1 += term1
    r2 += term2

    def _bp(trans: List[Tuple[str, int, float]], terminal: float) -> None:
        if not trans:
            return
        ls, la, lr = trans[-1]
        agent.update(ls, la, lr + terminal, "", [], done=True)
        for i in range(len(trans) - 2, -1, -1):
            s, a, r = trans[i]
            ns, na, _ = trans[i + 1]
            nq = agent._get_q(ns, na)
            target = r + agent.gamma * nq
            curr_q = agent._get_q(s, a)
            agent._set_q(s, a, curr_q + agent.alpha * (target - curr_q))

    _bp(trans_p1, term1)
    _bp(trans_p2, term2)
    return winner, r1, r2


def evaluate_agent(agent: QLearningAgent, n_eval: int = 100) -> float:
    """Evaluate the agent against a mixed opponent schedule."""

    def opp_rand(g):
        return random_move(g)

    def opp_ab2(g):
        return alpha_beta_move(g, depth=2)

    def opp_ab3(g):
        return alpha_beta_move(g, depth=3)

    half = n_eval // 2
    quarter = n_eval // 4

    schedule = (
        [(1, opp_rand)] * (half // 2)
        + [(2, opp_rand)] * (half // 2)
        + [(1, opp_ab2)] * (quarter // 2)
        + [(2, opp_ab2)] * (quarter // 2)
        + [(1, opp_ab3)] * (quarter // 2)
        + [(2, opp_ab3)] * (quarter // 2)
    )
    random.shuffle(schedule)

    wins = sum(
        1
        for (pos, fn) in schedule
        if run_episode(agent, fn, pos, update_agent=False)[0] == pos
    )
    return wins / len(schedule)


def _champion_check(agent: QLearningAgent, phase_name: str) -> None:
    """Evaluate the agent and persist the best checkpoint if needed."""
    print(f"\n[Champion] Évaluation après {phase_name}…")
    rate = evaluate_agent(agent, n_eval=100)
    print(
        f"[Champion] Taux de victoire = {rate:.1%}  "
        f"(record = {agent.best_win_rate:.1%})"
    )
    if rate > agent.best_win_rate:
        agent.best_win_rate = rate
        agent.save_best()
        print("[Champion] ** Nouveau record ! q_table_best.json mis a jour.")
    agent.save_latest()


EPSILON_BUMP = 0.15  # Remontée epsilon lors du changement de phase


def _train_phase(
    agent: QLearningAgent,
    phase_name: str,
    episodes: int,
    opp_fn,
    epsilon_restart: Optional[float] = None,
) -> None:
    """Train the agent for a fixed number of episodes against one opponent."""
    agent.set_epsilon_decay(episodes, start=epsilon_restart)
    wins = draws = losses = 0
    t0 = time.time()
    print(f"\n{'='*60}")
    print(f"[Phase] {phase_name}  ({episodes} ep, eps_init={agent.epsilon:.3f})")
    print(f"{'='*60}")

    for ep in range(1, episodes + 1):
        pos = random.choice([1, 2])
        winner, _ = run_episode(agent, opp_fn, pos, update_agent=True)
        agent.decay_epsilon()
        agent.total_episodes += 1

        if winner == pos:
            wins += 1
        elif winner is None:
            draws += 1
        else:
            losses += 1

        if ep % SAVE_EVERY == 0:
            agent.save_latest()
            wr = wins / ep
            print(
                f"  ep {ep:>5}/{episodes} | ε={agent.epsilon:.4f} | "
                f"V={wins} N={draws} D={losses} | "
                f"win%={wr:.1%} | {time.time()-t0:.0f}s | "
                f"états={len(agent.q_table)}"
            )

    agent.save_latest()
    total = wins + draws + losses
    print(
        f"\n[Phase {phase_name}] Fin : "
        f"V={wins}/{total} ({wins/total:.1%})  N={draws}  D={losses}"
    )


def _train_selfplay_phase(
    agent: QLearningAgent,
    episodes: int,
    epsilon_restart: Optional[float] = None,
) -> None:
    """Phase de Self-Play."""
    agent.set_epsilon_decay(episodes, start=epsilon_restart)
    w1 = w2 = draws = 0
    t0 = time.time()
    print(f"\n{'='*60}")
    print(f"[Phase] Self-Play  ({episodes} ep, eps_init={agent.epsilon:.3f})")
    print(f"{'='*60}")

    for ep in range(1, episodes + 1):
        winner, _, _ = run_selfplay_episode(agent)
        agent.decay_epsilon()
        agent.total_episodes += 1

        if winner == 1:
            w1 += 1
        elif winner == 2:
            w2 += 1
        else:
            draws += 1

        if ep % SAVE_EVERY == 0:
            agent.save_latest()
            print(
                f"  ep {ep:>5}/{episodes} | ε={agent.epsilon:.4f} | "
                f"J1={w1} J2={w2} N={draws} | "
                f"{time.time()-t0:.0f}s | états={len(agent.q_table)}"
            )

    agent.save_latest()
    total = w1 + w2 + draws
    print(f"\n[Self-Play] Fin : J1={w1} J2={w2} N={draws}/{total}")


# ===========================================================================
# Pipeline Curriculum complet
# ===========================================================================


def run_curriculum(agent: Optional[QLearningAgent] = None) -> QLearningAgent:
    """
    Lance le pipeline d'entraînement progressif complet.

    Phases
    ------
    1. vs Random            : 1 000 parties
    2. vs Alpha-Beta d=1-5  :   500 parties × 5 profondeurs
    3. Self-Play            : 1 000 parties

    À chaque changement de phase, epsilon remonte de EPSILON_BUMP (0.15).
    Évaluation "Champion" après chaque phase.

    Returns
    -------
    QLearningAgent entraîné.
    """
    if agent is None:
        agent = QLearningAgent()

    eps1 = min(1.0, agent.epsilon + EPSILON_BUMP)
    _train_phase(
        agent,
        phase_name="1 – vs Random",
        episodes=1_000,
        opp_fn=random_move,
        epsilon_restart=eps1,
    )
    _champion_check(agent, "Phase 1 – vs Random")

    for depth in range(1, 6):
        eps_d = min(1.0, agent.epsilon + EPSILON_BUMP)

        def _make_opp(d: int):
            return lambda g: alpha_beta_move(g, depth=d)

        _train_phase(
            agent,
            phase_name=f"2.{depth} – vs Alpha-Beta (prof. {depth})",
            episodes=500,
            opp_fn=_make_opp(depth),
            epsilon_restart=eps_d,
        )
        _champion_check(agent, f"Phase 2.{depth} – vs AB-{depth}")

    eps3 = min(1.0, agent.epsilon + EPSILON_BUMP)
    _train_selfplay_phase(agent, episodes=1_000, epsilon_restart=eps3)
    _champion_check(agent, "Phase 3 – Self-Play")

    print("\n[Curriculum] Entrainement complet termine.")
    print(f"  Total episodes : {agent.total_episodes}")
    print(f"  Etats appris   : {len(agent.q_table)}")
    print(f"  Meilleur taux  : {agent.best_win_rate:.1%}")
    return agent


if __name__ == "__main__":
    print("=== Démarrage du pipeline Q-Learning Awélé ===\n")
    trained_agent = run_curriculum()
    print("\n=== Pipeline terminé. Q-Table sauvegardée. ===")
