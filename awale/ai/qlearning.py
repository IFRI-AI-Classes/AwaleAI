"""Persistent Q-learning agent for Awalé."""

from __future__ import annotations

import json
import math
import os
import random
import time
import tempfile
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
    start = 0 if game.current_player == 1 else 6
    if type(hole) is not int or not start <= hole < start + 6:
        raise ValueError("L'action doit appartenir au joueur actif.")
    return hole - start


def decode_action(game: Game, relative_action: int) -> int:
    """
    Convertit un indice relatif (0-5) en indice absolu (0-11)
    selon le joueur courant.
    """
    if type(relative_action) is not int or not 0 <= relative_action < 6:
        raise ValueError("L'action relative doit être un entier de 0 à 5.")
    return relative_action if game.current_player == 1 else relative_action + 6


class QLearningAgent:
    """Persistent Q-learning agent with symmetric state encoding."""

    def __init__(
        self,
        alpha: float = ALPHA,
        gamma: float = GAMMA,
        epsilon: float = EPSILON_START,
        epsilon_min: float = EPSILON_MIN,
        checkpoint: str = "best",
        model_dir=None,
        load_models: bool = True,
    ) -> None:
        if checkpoint not in ('best', 'latest'):
            raise ValueError("checkpoint doit être 'best' ou 'latest'.")
        self.checkpoint = checkpoint
        self.loaded_path = None
        self.alpha = alpha
        self.gamma = gamma
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min

        self.q_table: Dict[str, Dict[str, float]] = {}
        self.total_episodes: int = 0
        self.best_win_rate: float = 0.0
        self._epsilon_decay: float = 0.0
        self._latest_path = os.path.join(os.fspath(model_dir), 'q_table_latest.json') if model_dir is not None else PATH_LATEST
        self._best_path = os.path.join(os.fspath(model_dir), 'q_table_best.json') if model_dir is not None else PATH_BEST
        self._validate_parameters(alpha, gamma, epsilon, epsilon_min, self._epsilon_decay)
        if load_models:
            self.load()

    @staticmethod
    def _validate_parameters(alpha, gamma, epsilon, epsilon_min, decay):
        for name, value, low, high in (
            ('alpha', alpha, 0, 1), ('gamma', gamma, 0, 1),
            ('epsilon', epsilon, 0, 1), ('epsilon_min', epsilon_min, 0, 1),
            ('epsilon_decay', decay, 0, float('inf')),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name} doit être un nombre fini.")
            if not low <= value <= high or (name == 'alpha' and value == 0):
                raise ValueError(f"{name} hors limites.")
        if epsilon < epsilon_min:
            raise ValueError("epsilon doit être supérieur ou égal à epsilon_min.")

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

    def choose_move(self, game: Game, greedy: bool = False) -> Optional[int]:
        """
        Choose an absolute move index via epsilon-greedy.

        Args:
            game: Current game state.
            greedy: Force pure exploitation when True.

        Returns:
            int: Selected absolute hole index.
        """
        valid_abs = game.get_valid_moves()
        if not valid_abs:
            return None

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
        if type(done) is not bool or not isinstance(state, str) or not state or not isinstance(next_state, str):
            raise ValueError("État ou indicateur terminal invalide.")
        if type(action_rel) is not int or not 0 <= action_rel < 6:
            raise ValueError("Action relative invalide.")
        if isinstance(reward, bool) or not isinstance(reward, (int, float)) or not math.isfinite(reward):
            raise ValueError("La récompense doit être finie.")
        if not done and (not next_state or not next_valid_actions):
            raise ValueError("Une transition non terminale exige un état et des actions légales.")
        if any(type(a) is not int or not 0 <= a < 6 for a in next_valid_actions):
            raise ValueError("Actions suivantes invalides.")
        q_current = self._get_q(state, action_rel)
        target = reward
        if not done:
            target += self.gamma * self._max_q(next_state, next_valid_actions)
        self._set_q(state, action_rel, q_current + self.alpha * (target - q_current))

    def set_epsilon_decay(self, n_episodes: int, start: Optional[float] = None) -> None:
        """Configure the linear epsilon decay over a fixed number of episodes."""
        if type(n_episodes) is not int or n_episodes < 1:
            raise ValueError("n_episodes doit être un entier positif.")
        if start is not None:
            self._validate_parameters(self.alpha, self.gamma, start, self.epsilon_min, 0)
            self.epsilon = min(1.0, max(self.epsilon_min, start))
        span = max(self.epsilon - self.epsilon_min, 0.0)
        self._epsilon_decay = span / n_episodes

    def decay_epsilon(self) -> None:
        """Apply one linear epsilon decay step."""
        self.epsilon = max(self.epsilon_min, self.epsilon - self._epsilon_decay)

    def _checkpoint_payload(self):
        return {
            "schema_version": 2,
            "state_encoding": "relative-pits-scores-v1",
            "alpha": self.alpha, "gamma": self.gamma,
            "epsilon": self.epsilon, "epsilon_min": self.epsilon_min,
            "epsilon_decay": self._epsilon_decay,
            "total_episodes": self.total_episodes,
            "best_win_rate": self.best_win_rate,
            "q_table": self.q_table,
        }

    def _validated_checkpoint(self, data):
        if not isinstance(data, dict) or type(data.get("schema_version", 1)) is not int or data.get("schema_version", 1) not in (1, 2):
            raise ValueError("Format de checkpoint non supporté.")
        if data.get("state_encoding", "relative-pits-scores-v1") != "relative-pits-scores-v1":
            raise ValueError("Encodage d'état incompatible.")
        table = data.get("q_table", {})
        if not isinstance(table, dict):
            raise ValueError("q_table doit être un dictionnaire.")
        valid_actions = {str(i) for i in range(6)}
        for state, actions in table.items():
            if not isinstance(state, str) or not isinstance(actions, dict):
                raise ValueError("État ou actions mal formés.")
            for action, value in actions.items():
                if action not in valid_actions:
                    raise ValueError("Action persistée hors limites.")
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError("Valeur Q non finie ou invalide.")
        params = {name: data.get(name, getattr(self, name))
                  for name in ("alpha", "gamma", "epsilon", "epsilon_min")}
        decay = data.get("epsilon_decay", 0.0)
        self._validate_parameters(**params, decay=decay)
        episodes = data.get("total_episodes", 0)
        rate = data.get("best_win_rate", 0.0)
        if type(episodes) is not int or episodes < 0:
            raise ValueError("Compteur d'épisodes invalide.")
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate) or not 0 <= rate <= 1:
            raise ValueError("Taux de victoire invalide.")
        return table, params, decay, episodes, rate

    def save(self, path: str) -> None:
        """Atomically save parameters and table to the explicit destination."""
        payload = self._checkpoint_payload()
        self._validated_checkpoint(payload)
        destination = os.path.abspath(os.fspath(path))
        parent = os.path.dirname(destination)
        os.makedirs(parent, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=parent,
                                             prefix=".q-table-", suffix=".tmp", delete=False) as f:
                temporary = f.name
                json.dump(payload, f, separators=(",", ":"), allow_nan=False)
            os.replace(temporary, destination)
        finally:
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)

    def load(self) -> None:
        """Validate completely before loading; accept legacy version-1 tables."""
        paths = [self._best_path, self._latest_path] if self.checkpoint == 'best' else [self._latest_path, self._best_path]
        for path in paths:
            norm = os.path.normpath(path)
            if os.path.isfile(norm):
                try:
                    with open(norm, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    table, params, decay, episodes, rate = self._validated_checkpoint(data)
                    self.q_table = table
                    for name, value in params.items():
                        setattr(self, name, value)
                    self._epsilon_decay = decay
                    self.total_episodes = episodes
                    self.best_win_rate = rate
                    self.loaded_path = norm
                    print(f"[QLearning] Chargé depuis {os.path.basename(norm)} "
                          f"| {len(table)} états | ε={self.epsilon:.3f} | épisodes={episodes}")
                    return
                except (OSError, ValueError, TypeError) as exc:
                    print(f"[QLearning] Erreur lecture {norm}: {exc}")
        print("[QLearning] Démarrage avec une Q-Table vide.")

    def save_latest(self) -> None:
        self.save(self._latest_path)

    def save_best(self) -> None:
        self.save(self._best_path)

def _opponent_move(game, opp_move_fn):
    """Accept either an absolute move or a search agent's (move, nodes)."""
    result = opp_move_fn(game)
    if isinstance(result, tuple) and len(result) != 2:
        raise ValueError("L'adversaire doit renvoyer un coup ou (coup, nœuds).")
    move = result[0] if isinstance(result, tuple) else result
    if not game.play_move(move):
        raise ValueError(f"L'adversaire a renvoyé un coup invalide : {result}")
    return move


def _opp_captures_after(game: Game, opp_move_fn) -> int:
    """Simulate a legal reply without swallowing agent errors."""
    sim = game.copy()
    if sim.is_game_over():
        return 0
    opp = sim.current_player
    before = sim.score_p1 if opp == 1 else sim.score_p2
    _opponent_move(sim, opp_move_fn)
    after = sim.score_p1 if opp == 1 else sim.score_p2
    return after - before


def run_episode(agent, opp_move_fn, agent_player, update_agent=True):
    """Learn transitions between this agent's turns, using the actual reply."""
    if agent_player not in (1, 2):
        raise ValueError("agent_player doit être 1 ou 2.")
    game = Game()
    total_reward = 0.0
    if game.current_player != agent_player:
        _opponent_move(game, opp_move_fn)

    while not game.is_game_over():
        state = encode_state(game)
        before = game.score_p1 if agent_player == 1 else game.score_p2
        hole = agent.choose_move(game, greedy=not update_agent)
        action = encode_action(game, hole)
        if not game.play_move(hole):
            raise ValueError(f"L'agent a renvoyé un coup invalide : {hole}")
        after = game.score_p1 if agent_player == 1 else game.score_p2
        reward = R_TIME + R_CAPTURE * (after - before)

        if not game.is_game_over():
            opp = game.current_player
            before_opp = game.score_p1 if opp == 1 else game.score_p2
            _opponent_move(game, opp_move_fn)
            after_opp = game.score_p1 if opp == 1 else game.score_p2
            reward += R_OPP_CAP * (after_opp - before_opp)

        done = game.is_game_over()
        if done:
            winner = game.get_winner()
            reward += R_DRAW if winner is None else R_WIN if winner == agent_player else R_LOSS
            next_state, actions = "", []
        else:
            next_state = encode_state(game)
            actions = [encode_action(game, m) for m in game.get_valid_moves()]
        if update_agent:
            agent.update(state, action, reward, next_state, actions, done)
        total_reward += reward
    return game.get_winner(), total_reward


def run_selfplay_episode(agent):
    """Learn one transition per player, after the other player's reply."""
    game = Game()
    pending = {}
    rewards = {1: 0.0, 2: 0.0}
    while not game.is_game_over():
        p = game.current_player
        if p in pending:
            state, action, reward = pending.pop(p)
            actions = [encode_action(game, m) for m in game.get_valid_moves()]
            agent.update(state, action, reward, encode_state(game), actions, False)
            rewards[p] += reward
        state = encode_state(game)
        hole = agent.choose_move(game, greedy=False)
        action = encode_action(game, hole)
        before = game.score_p1 if p == 1 else game.score_p2
        if not game.play_move(hole):
            raise ValueError(f"L'agent a renvoyé un coup invalide : {hole}")
        after = game.score_p1 if p == 1 else game.score_p2
        captured = after - before
        pending[p] = (state, action, R_TIME + R_CAPTURE * captured)
        opp = 3 - p
        if opp in pending:
            s, a, r = pending[opp]
            pending[opp] = (s, a, r + R_OPP_CAP * captured)

    winner = game.get_winner()
    for p, (state, action, reward) in pending.items():
        reward += R_DRAW if winner is None else R_WIN if winner == p else R_LOSS
        agent.update(state, action, reward, "", [], True)
        rewards[p] += reward
    return winner, rewards[1], rewards[2]


def evaluate_agent(agent: QLearningAgent, n_eval: int = 100) -> float:
    """Evaluate the agent against a mixed opponent schedule."""

    def opp_rand(g):
        return random_move(g)

    def opp_ab2(g):
        return alpha_beta_move(g, depth=2)[0]

    def opp_ab3(g):
        return alpha_beta_move(g, depth=3)[0]

    if type(n_eval) is not int or n_eval < 1:
        raise ValueError("n_eval doit être un entier positif.")
    cycle = [(1, opp_rand), (2, opp_rand)] * 2 + [
        (1, opp_ab2), (2, opp_ab2), (1, opp_ab3), (2, opp_ab3)
    ]
    schedule = [cycle[i % len(cycle)] for i in range(n_eval)]
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
        agent = QLearningAgent(checkpoint="latest")

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
            return lambda g: alpha_beta_move(g, depth=d)[0]

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
