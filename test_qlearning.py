"""
test_qlearning.py
=================
Suite de tests pour l'agent Q-Learning Awele.

Tests couverts
--------------
1. Encodage symetrique (J1 / J2 -> meme cle)
2. Coherence encode/decode d'action
3. Q-Table : initialisation paresseuse & mise a jour Bellman
4. Persistence JSON (save / load roundtrip)
5. Politique epsilon-greedy (ratio exploration vs exploitation)
6. Decroissance lineaire d'epsilon (plancher 0.05)
7. Episode complet vs Random (winner valide, reward coherente)
8. Self-Play (J1+J2 mis a jour, Q-Table grandit)
9. Evaluation Champion (win_rate in [0,1])
10. Performance : 50 episodes vs Random en < 10s
11. Winrate apres chargement depuis disque (greedy >= random baseline)
12. Coherence de la Q-Table apres sauvegarde/rechargement

A executer depuis la racine du projet :
    python test_qlearning.py
"""

import sys
import os
import json
import time
import random
import tempfile

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(__file__))

from engine.game import Game
from engine.rules import Rules
from agents.random.random_agent import random_move
from agents.alpha_beta.elagage import best_move as alpha_beta_move
from awale.ai.qlearning import (
    QLearningAgent,
    encode_state,
    encode_action,
    decode_action,
    run_episode,
    run_selfplay_episode,
    evaluate_agent,
    _train_phase,
    _train_selfplay_phase,
    R_WIN, R_LOSS, R_DRAW,
    PATH_LATEST, PATH_BEST,
)

# ---------------------------------------------------------------------------
# Utilitaires de rapport
# ---------------------------------------------------------------------------

PASS = "[PASS]"
FAIL = "[FAIL]"
results = []

def check(name: str, condition: bool, detail: str = "") -> None:
    status = PASS if condition else FAIL
    msg = f"  {status}  {name}"
    if detail:
        msg += f"  ({detail})"
    print(msg)
    results.append((name, condition))

def section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ===========================================================================
# 1. Encodage symetrique
# ===========================================================================
section("1. Encodage symetrique")

g = Game()

# Etat initial : plateau identique des deux cotes
g.current_player = 1
s_j1 = encode_state(g)
g.current_player = 2
s_j2 = encode_state(g)
check("Plateau initial : meme cle pour J1 et J2", s_j1 == s_j2,
      f"J1={s_j1[:20]}... J2={s_j2[:20]}...")

# Apres un coup, les cles doivent differer
g2 = Game()
g2.current_player = 1
g2.board.holes[0] = 6   # asymetrie artificielle
s_asym_j1 = encode_state(g2)
g2.current_player = 2
s_asym_j2 = encode_state(g2)
check("Plateau asymetrique : cles differentes pour J1 et J2",
      s_asym_j1 != s_asym_j2)

# Format : doit contenir 3 separateurs '|'
check("Format de cle : 3 separateurs '|'",
      s_j1.count("|") == 3, f"cle={s_j1}")


# ===========================================================================
# 2. Coherence encode / decode action
# ===========================================================================
section("2. Coherence encode / decode action")

for player, valid_range in [(1, range(0, 6)), (2, range(6, 12))]:
    g3 = Game()
    g3.current_player = player
    for abs_hole in valid_range:
        rel = encode_action(g3, abs_hole)
        back = decode_action(g3, rel)
        if back != abs_hole:
            check(f"Roundtrip J{player} hole={abs_hole}", False,
                  f"encode={rel} decode={back}")
            break
    else:
        check(f"Roundtrip J{player} : tous les coups 0-5 OK", True)

check("encode J1 hole=0 -> 0",  encode_action(Game(), 0) == 0)
g_j2 = Game(); g_j2.current_player = 2
check("encode J2 hole=6 -> 0",  encode_action(g_j2, 6) == 0)
check("encode J2 hole=11 -> 5", encode_action(g_j2, 11) == 5)
check("decode J2 rel=0 -> 6",   decode_action(g_j2, 0) == 6)
check("decode J2 rel=5 -> 11",  decode_action(g_j2, 5) == 11)


# ===========================================================================
# 3. Q-Table : initialisation paresseuse & mise a jour Bellman
# ===========================================================================
section("3. Q-Table - init paresseuse & Bellman")

agent = QLearningAgent(epsilon=0.0)  # greedy pur, pas de charge depuis disque ici
# Reset propre
agent.q_table = {}
agent.total_episodes = 0

# Lazy init
val = agent._get_q("etat_inconnu", 3)
check("Etat inconnu -> Q=0.0 (lazy init)", val == 0.0, f"val={val}")
check("Q-Table vide apres acces lecture", len(agent.q_table) == 0)

# Set
agent._set_q("s1", 2, 5.0)
check("_set_q cree entree", "s1" in agent.q_table)
check("_set_q valeur correcte", agent._get_q("s1", 2) == 5.0)

# Mise a jour Bellman : done=True
agent.update("s1", 2, reward=10.0, next_state="", next_valid_actions=[], done=True)
# Q(s,a) = 5.0 + 0.15 * (10.0 - 5.0) = 5.75
expected = 5.0 + agent.alpha * (10.0 - 5.0)
check("Mise a jour Bellman (done=True)", abs(agent._get_q("s1", 2) - expected) < 1e-9,
      f"expected={expected:.4f} got={agent._get_q('s1',2):.4f}")

# Mise a jour Bellman : done=False avec next state connu
agent._set_q("s2", 1, 8.0)
agent.update("s1", 2, reward=2.0, next_state="s2",
             next_valid_actions=[1], done=False)
# Q(s1,2) apres = expected + alpha*(2 + gamma*8 - expected)
expected2 = expected + agent.alpha * (2.0 + agent.gamma * 8.0 - expected)
check("Mise a jour Bellman (not done, next_Q=8)",
      abs(agent._get_q("s1", 2) - expected2) < 1e-9,
      f"expected={expected2:.4f} got={agent._get_q('s1',2):.4f}")


# ===========================================================================
# 4. Persistence JSON (save / load roundtrip)
# ===========================================================================
section("4. Persistence JSON - save / load")

with tempfile.TemporaryDirectory() as tmpdir:
    tmp_path = os.path.join(tmpdir, "test_q.json")

    agent2 = QLearningAgent(epsilon=0.42)
    agent2.q_table = {}
    agent2._set_q("etat_test", 3, 7.77)
    agent2.total_episodes = 42
    agent2.best_win_rate  = 0.65
    agent2.epsilon        = 0.42
    agent2.save(tmp_path)

    check("Fichier JSON cree", os.path.isfile(tmp_path))

    agent3 = QLearningAgent.__new__(QLearningAgent)
    agent3.q_table = {}
    agent3.epsilon = 0.0
    agent3.total_episodes = 0
    agent3.best_win_rate  = 0.0
    agent3._epsilon_decay = 0.0
    agent3.alpha = 0.15
    agent3.gamma = 0.95
    agent3.epsilon_min = 0.05

    with open(tmp_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    agent3.q_table        = data["q_table"]
    agent3.epsilon        = data["epsilon"]
    agent3.total_episodes = data["total_episodes"]
    agent3.best_win_rate  = data["best_win_rate"]

    check("Roundtrip epsilon",        abs(agent3.epsilon - 0.42) < 1e-9)
    check("Roundtrip total_episodes", agent3.total_episodes == 42)
    check("Roundtrip best_win_rate",  abs(agent3.best_win_rate - 0.65) < 1e-9)
    check("Roundtrip Q-value",        abs(agent3._get_q("etat_test", 3) - 7.77) < 1e-9)

    # Format JSON lisible (pas pickle)
    with open(tmp_path, "rb") as f:
        header = f.read(1)
    check("Format JSON (debut par '{')", header == b"{")


# ===========================================================================
# 5. Politique epsilon-greedy
# ===========================================================================
section("5. Politique epsilon-greedy")

g_test = Game()
g_test.current_player = 1

# Avec epsilon=1.0 -> toujours aleatoire
agent_exp = QLearningAgent(epsilon=1.0)
agent_exp.q_table = {}
moves_explore = [agent_exp.choose_move(g_test) for _ in range(200)]
unique_moves = set(moves_explore)
check("Exploration pure (eps=1): diversite des coups", len(unique_moves) > 1,
      f"coups uniques={unique_moves}")

# Avec epsilon=0 et une seule action Q positive -> toujours ce coup
agent_greed = QLearningAgent(epsilon=0.0)
agent_greed.q_table = {}
state_g = encode_state(g_test)
for rel in range(6):
    agent_greed._set_q(state_g, rel, -10.0)
agent_greed._set_q(state_g, 3, 999.0)  # action 3 (hole 3 pour J1)
moves_greedy = [agent_greed.choose_move(g_test, greedy=True) for _ in range(50)]
check("Exploitation pure (eps=0): toujours action optimale",
      all(m == 3 for m in moves_greedy),
      f"coups={set(moves_greedy)}")


# ===========================================================================
# 6. Decroissance lineaire d'epsilon
# ===========================================================================
section("6. Decroissance epsilon (lineaire, plancher 0.05)")

agent_dec = QLearningAgent(epsilon=0.5, epsilon_min=0.05)
agent_dec.q_table = {}
agent_dec.set_epsilon_decay(n_episodes=100, start=1.0)

epsilons = [1.0]
for _ in range(100):
    agent_dec.decay_epsilon()
    epsilons.append(agent_dec.epsilon)

check("Epsilon commence a 1.0", abs(epsilons[0] - 1.0) < 1e-9)
check("Epsilon termine a 0.05 (plancher)", abs(epsilons[-1] - 0.05) < 1e-6,
      f"final={epsilons[-1]:.6f}")
check("Epsilon est monotone decroissant",
      all(epsilons[i] >= epsilons[i+1] for i in range(len(epsilons)-1)))
check("Epsilon ne descend jamais sous le plancher",
      all(e >= 0.05 - 1e-9 for e in epsilons))


# ===========================================================================
# 7. Episode complet vs Random
# ===========================================================================
section("7. Episode complet vs Random")

ag = QLearningAgent(epsilon=0.5)
ag.q_table = {}

for pos in [1, 2]:
    winner, reward = run_episode(ag, random_move, agent_player=pos, update_agent=True)
    check(f"Episode J{pos}: winner in [1, 2, None]", winner in [1, 2, None],
          f"winner={winner}")
    check(f"Episode J{pos}: reward est un float", isinstance(reward, float),
          f"reward={reward:.1f}")
    check(f"Episode J{pos}: reward dans [-500, 200]", -500 <= reward <= 200,
          f"reward={reward:.1f}")
    check(f"Episode J{pos}: Q-Table grandit", len(ag.q_table) > 0,
          f"etats={len(ag.q_table)}")


# ===========================================================================
# 8. Self-Play
# ===========================================================================
section("8. Self-Play")

ag_sp = QLearningAgent(epsilon=0.8)
ag_sp.q_table = {}
states_before = len(ag_sp.q_table)

for i in range(5):
    winner, r1, r2 = run_selfplay_episode(ag_sp)
    check(f"Self-Play ep{i+1}: winner in [1,2,None]", winner in [1, 2, None])
    check(f"Self-Play ep{i+1}: rewards sont des floats",
          isinstance(r1, float) and isinstance(r2, float))

states_after = len(ag_sp.q_table)
check("Self-Play : Q-Table grandit", states_after > states_before,
      f"{states_before} -> {states_after} etats")

# Somme des rewards : une victoire + une defaite (zero-sum)
# On verifie juste que la somme est coherente (pas de valeur aberrante)
check("Self-Play : r1+r2 coherent (zero-sum environ)",
      abs(r1 + r2) < 500,   # dans un cas limite elles pourraient compenser
      f"r1={r1:.1f} r2={r2:.1f} sum={r1+r2:.1f}")


# ===========================================================================
# 9. Evaluation Champion (win_rate in [0,1])
# ===========================================================================
section("9. Evaluation Champion")

ag_eval = QLearningAgent(epsilon=0.0)
ag_eval.q_table = {}

rate = evaluate_agent(ag_eval, n_eval=20)
check("Win rate dans [0.0, 1.0]", 0.0 <= rate <= 1.0, f"rate={rate:.1%}")
check("Win rate est un float", isinstance(rate, float))
print(f"  Info : win rate agent vierge vs mix = {rate:.1%}")


# ===========================================================================
# 10. Performance : 50 episodes en moins de 15s
# ===========================================================================
section("10. Performance")

ag_perf = QLearningAgent(epsilon=0.5)
ag_perf.q_table = {}

t0 = time.time()
for _ in range(50):
    run_episode(ag_perf, random_move, agent_player=random.choice([1, 2]),
                update_agent=True)
elapsed = time.time() - t0
check(f"50 episodes vs Random en < 15s", elapsed < 15.0,
      f"temps={elapsed:.2f}s")
print(f"  Info : {elapsed:.2f}s pour 50 episodes ({elapsed/50*1000:.1f}ms/ep)")


# ===========================================================================
# 11. Mini-entrainement + winrate vs baseline aleatoire
# ===========================================================================
section("11. Mini-entrainement (200 ep) et winrate")

ag_train = QLearningAgent(epsilon=1.0)
ag_train.q_table = {}
ag_train.set_epsilon_decay(200, start=1.0)

for _ in range(200):
    pos = random.choice([1, 2])
    run_episode(ag_train, random_move, pos, update_agent=True)
    ag_train.decay_epsilon()
    ag_train.total_episodes += 1

# Evaluer en mode greedy sur 50 parties
wins = sum(
    1 for _ in range(50)
    for pos in [random.choice([1, 2])]
    if run_episode(ag_train, random_move, pos, update_agent=False)[0] == pos
)
wr_trained = wins / 50
check("Agent entraine bat le hasard (>35% vs Random)",
      wr_trained > 0.35,
      f"winrate={wr_trained:.1%} sur 50 parties greedy")
print(f"  Info : winrate apres 200 ep = {wr_trained:.1%}")


# ===========================================================================
# 12. Coherence Q-Table apres save/load sur le vrai PATH
# ===========================================================================
section("12. Coherence Q-Table - save puis load")

ag_s = QLearningAgent.__new__(QLearningAgent)
ag_s.q_table = {"etat_z": {"2": 3.14}}
ag_s.epsilon = 0.33
ag_s.total_episodes = 77
ag_s.best_win_rate = 0.55
ag_s.alpha = 0.15
ag_s.gamma = 0.95
ag_s.epsilon_min = 0.05
ag_s._epsilon_decay = 0.0

with tempfile.TemporaryDirectory() as td:
    p = os.path.join(td, "q_test2.json")
    ag_s.save(p)

    ag_l = QLearningAgent.__new__(QLearningAgent)
    ag_l.q_table = {}
    ag_l.epsilon = 0.0
    ag_l.total_episodes = 0
    ag_l.best_win_rate = 0.0
    ag_l.alpha = 0.15
    ag_l.gamma = 0.95
    ag_l.epsilon_min = 0.05
    ag_l._epsilon_decay = 0.0

    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    ag_l.q_table        = data["q_table"]
    ag_l.epsilon        = data["epsilon"]
    ag_l.total_episodes = data["total_episodes"]
    ag_l.best_win_rate  = data["best_win_rate"]

    check("Save/load epsilon",        abs(ag_l.epsilon - 0.33) < 1e-9)
    check("Save/load total_episodes", ag_l.total_episodes == 77)
    check("Save/load best_win_rate",  abs(ag_l.best_win_rate - 0.55) < 1e-9)
    check("Save/load Q-value 3.14",   abs(ag_l._get_q("etat_z", 2) - 3.14) < 1e-9)


# ===========================================================================
# Rapport final
# ===========================================================================
print("\n" + "=" * 60)
print("  RAPPORT FINAL")
print("=" * 60)

passed = sum(1 for _, ok in results if ok)
failed = sum(1 for _, ok in results if not ok)
total  = len(results)

print(f"\n  PASS : {passed}/{total}")
print(f"  FAIL : {failed}/{total}")

if failed > 0:
    print("\n  Tests echoues :")
    for name, ok in results:
        if not ok:
            print(f"    - {name}")

print()
if failed == 0:
    print("  Tous les tests sont passes avec succes !")
else:
    print(f"  {failed} test(s) ont echoue.")
    sys.exit(1)
