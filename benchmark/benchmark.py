"""
Benchmark des agents AwaleAI — tournoi toutes-rondes sur N parties par duel.

Ce script N'ALTÈRE AUCUN fichier existant du projet : il se contente
d'importer le moteur (engine/) et le routeur d'agents (agents/difficulty.py),
exactement comme le fait l'API FastAPI.

Protocole
---------
* Agents : Aléatoire, Minimax, Alpha-Bêta, Q-Learning (glouton, sans exploration).
* Chaque paire d'agents s'affronte sur ``--games`` parties (50 par défaut).
* Minimax et Alpha-Bêta sont déterministes : sans variation, les 50 parties
  seraient identiques. On utilise donc des **ouvertures aléatoires** :
  les ``--opening-plies`` premiers demi-coups (2 par défaut) sont tirés au
  hasard, puis les agents prennent la main.
* Équité : chaque ouverture est jouée **deux fois en inversant les couleurs**
  (25 ouvertures × 2 = 50 parties) → chaque agent commence 25 fois.
* Une partie est déclarée nulle en cas de répétition de position ou si elle
  dépasse ``--max-plies`` demi-coups (même logique que main.py).
* Mesures : victoires / nuls / défaites, graines finales, nombre de coups,
  temps moyen de décision par coup, nœuds explorés par coup.
* Expérience complémentaire : sur des positions tirées de parties réelles,
  on compare le coup choisi par Minimax et par Alpha-Bêta à profondeur égale
  ainsi que le nombre de nœuds explorés.

Usage
-----
    python -m benchmark.benchmark                 # 50 parties par duel
    python -m benchmark.benchmark --games 20 --depth 3
    python -m benchmark.benchmark --workers 4 --seed 7

Les résultats sont écrits dans ``benchmark/results/`` :
    results.json, games.csv, RESULTS.md, winrate.svg
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import itertools
import json
import os
import random
import statistics
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional

# Permet de lancer le script depuis n'importe où (python benchmark/benchmark.py)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.chdir(ROOT)  # qlearning.py charge models/ en chemin relatif

from engine.game import Game  # noqa: E402
from engine.rules import Rules  # noqa: E402
from agents import difficulty  # noqa: E402

AGENT_ORDER = ["random", "minimax", "alphabeta", "qlearning"]
LABELS = {
    "random": "Aléatoire",
    "minimax": "Minimax",
    "alphabeta": "Alpha-Bêta",
    "qlearning": "Q-Learning",
}


# ─────────────────────────────────────────────────────────────────────────────
# Structures
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class GameResult:
    agent_a: str
    agent_b: str
    a_is_p1: bool
    opening_id: int
    winner: Optional[str]          # nom de l'agent gagnant ou None (nul)
    end_reason: str                # score | blocage | repetition | limite
    seeds_a: int
    seeds_b: int
    plies: int
    time_a: float                  # temps total de décision de A (s)
    time_b: float
    moves_a: int                   # coups joués par A (hors ouverture)
    moves_b: int
    nodes_a: int
    nodes_b: int
    opening: list = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Moteur de partie
# ─────────────────────────────────────────────────────────────────────────────


def _final_scores(game: Game) -> tuple[int, int]:
    """Scores finaux (graines restantes attribuées en cas de blocage),
    identique à api/server.py::_game_to_state."""
    s1, s2 = game.score_p1, game.score_p2
    if not Rules.get_valid_moves(game.board, game.current_player):
        remaining = sum(game.board.holes)
        if game.current_player == 1:
            s2 += remaining
        else:
            s1 += remaining
    return s1, s2


def _silent_call(fn, *args, **kwargs):
    """Appelle fn en masquant les print() (ex. chargement de la Q-table)."""
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*args, **kwargs)


def make_opening(rng: random.Random, plies: int) -> list[int]:
    """Tire une ouverture aléatoire légale de ``plies`` demi-coups."""
    game = Game()
    moves = []
    for _ in range(plies):
        if game.is_game_over():
            break
        mv = rng.choice(Rules.get_valid_moves(game.board, game.current_player))
        game.play_move(mv)
        moves.append(mv)
    return moves


def play_game(agent_p1: str, agent_p2: str, depths: dict, opening: list[int],
              max_plies: int, seed: int):
    """Joue une partie complète et renvoie les statistiques brutes."""
    random.seed(seed)  # agent aléatoire / départage éventuel
    game = Game()
    agents = {1: agent_p1, 2: agent_p2}
    t = {1: 0.0, 2: 0.0}
    n_moves = {1: 0, 2: 0}
    nodes = {1: 0, 2: 0}
    history = set()
    plies = 0

    for mv in opening:
        game.play_move(mv)
        plies += 1

    reason = None
    while True:
        if game.is_game_over():
            reason = "score" if max(game.score_p1, game.score_p2) >= 25 else "blocage"
            break
        state = (tuple(game.board.holes), game.score_p1, game.score_p2, game.current_player)
        if state in history:
            reason = "repetition"
            break
        history.add(state)
        if plies >= max_plies:
            reason = "limite"
            break

        p = game.current_player
        start = time.perf_counter()
        move, n = _silent_call(difficulty.choose_move_by_agent, game, agents[p], depths.get(agents[p]))
        t[p] += time.perf_counter() - start
        n_moves[p] += 1
        nodes[p] += n or 0

        if move is None or not game.play_move(move):
            raise RuntimeError(f"{agents[p]} a renvoyé un coup invalide : {move}")
        plies += 1

    s1, s2 = _final_scores(game)
    if reason in ("score", "blocage"):
        winner = 1 if s1 > s2 else 2 if s2 > s1 else None
    else:
        winner = None  # répétition / limite → nul
    return winner, reason, s1, s2, plies, t, n_moves, nodes


def run_match(job: dict) -> GameResult:
    """Exécute une partie (fonction appelée dans les processus workers)."""
    a, b, a_is_p1 = job["a"], job["b"], job["a_is_p1"]
    p1, p2 = (a, b) if a_is_p1 else (b, a)
    winner, reason, s1, s2, plies, t, nm, nd = play_game(
        p1, p2, job["depths"], job["opening"], job["max_plies"], job["seed"]
    )
    ia, ib = (1, 2) if a_is_p1 else (2, 1)
    win_name = None if winner is None else (a if winner == ia else b)
    sc = {1: s1, 2: s2}
    return GameResult(
        agent_a=a, agent_b=b, a_is_p1=a_is_p1, opening_id=job["opening_id"],
        winner=win_name, end_reason=reason,
        seeds_a=sc[ia], seeds_b=sc[ib], plies=plies,
        time_a=t[ia], time_b=t[ib], moves_a=nm[ia], moves_b=nm[ib],
        nodes_a=nd[ia], nodes_b=nd[ib], opening=job["opening"],
    )


def agreement_job(job: dict) -> dict:
    """Compare Minimax et Alpha-Bêta à profondeur égale sur une position."""
    game = Game()
    for mv in job["moves"]:
        game.play_move(mv)
    d = job["depth"]
    random.seed(job.get("seed", 0))
    t0 = time.perf_counter()
    m_mm, n_mm = _silent_call(difficulty.choose_move_by_agent, game, "minimax", d)
    t1 = time.perf_counter()
    m_ab, n_ab = _silent_call(difficulty.choose_move_by_agent, game, "alphabeta", d)
    t2 = time.perf_counter()

    # Valeur Minimax exacte de chaque coup racine → ensemble des coups optimaux.
    # Alpha-Bêta est correct si son coup appartient à cet ensemble (égalités).
    from agents.minimax.minimax import Minimax, SearchState
    mm = Minimax(depth=d)
    mm._nodes = 0
    root = SearchState(holes=game.board.holes[:], score1=game.score_p1,
                       score2=game.score_p2, player=game.current_player)
    values = {mv: mm.minimax(mm.apply_move(root, mv), d - 1, game.current_player)[0]
              for mv in mm.legal_moves(root)}
    best = max(values.values())
    optimal = {mv for mv, v in values.items() if abs(v - best) < 1e-9}
    return {"same": m_mm == m_ab, "ab_optimal": m_ab in optimal, "mm_optimal": m_mm in optimal,
            "ties": len(optimal) > 1,
            "nodes_mm": n_mm or 0, "nodes_ab": n_ab or 0,
            "time_mm": t1 - t0, "time_ab": t2 - t1}


def sample_positions(rng: random.Random, n: int, max_len: int = 40) -> list[list[int]]:
    """Positions variées obtenues par des séquences de coups aléatoires."""
    positions = []
    while len(positions) < n:
        game, moves = Game(), []
        for _ in range(rng.randint(2, max_len)):
            if game.is_game_over():
                break
            mv = rng.choice(Rules.get_valid_moves(game.board, game.current_player))
            game.play_move(mv)
            moves.append(mv)
        if not game.is_game_over():
            positions.append(moves)
    return positions


# ─────────────────────────────────────────────────────────────────────────────
# Agrégation
# ─────────────────────────────────────────────────────────────────────────────


def aggregate(results: list[GameResult], agents: list[str]) -> dict:
    duels = {}
    per_agent = {a: {"games": 0, "wins": 0, "draws": 0, "losses": 0,
                     "seeds_for": 0, "seeds_against": 0,
                     "time": 0.0, "moves": 0, "nodes": 0} for a in agents}

    for a, b in itertools.combinations(agents, 2):
        rs = [r for r in results if r.agent_a == a and r.agent_b == b]
        if not rs:
            continue
        wa = sum(r.winner == a for r in rs)
        wb = sum(r.winner == b for r in rs)
        dr = len(rs) - wa - wb
        duels[f"{a}|{b}"] = {
            "a": a, "b": b, "games": len(rs),
            "wins_a": wa, "wins_b": wb, "draws": dr,
            "win_rate_a": wa / len(rs), "win_rate_b": wb / len(rs),
            "avg_seeds_a": statistics.mean(r.seeds_a for r in rs),
            "avg_seeds_b": statistics.mean(r.seeds_b for r in rs),
            "avg_plies": statistics.mean(r.plies for r in rs),
            "wins_a_as_p1": sum(r.winner == a and r.a_is_p1 for r in rs),
            "wins_a_as_p2": sum(r.winner == a and not r.a_is_p1 for r in rs),
            "end_reasons": {k: sum(r.end_reason == k for r in rs)
                            for k in ("score", "blocage", "repetition", "limite")},
            "ms_per_move_a": 1000 * sum(r.time_a for r in rs) / max(1, sum(r.moves_a for r in rs)),
            "ms_per_move_b": 1000 * sum(r.time_b for r in rs) / max(1, sum(r.moves_b for r in rs)),
        }

    for r in results:
        for me, opp, side in ((r.agent_a, r.agent_b, "a"), (r.agent_b, r.agent_a, "b")):
            s = per_agent[me]
            s["games"] += 1
            if r.winner == me:
                s["wins"] += 1
            elif r.winner is None:
                s["draws"] += 1
            else:
                s["losses"] += 1
            s["seeds_for"] += r.seeds_a if side == "a" else r.seeds_b
            s["seeds_against"] += r.seeds_b if side == "a" else r.seeds_a
            s["time"] += r.time_a if side == "a" else r.time_b
            s["moves"] += r.moves_a if side == "a" else r.moves_b
            s["nodes"] += r.nodes_a if side == "a" else r.nodes_b

    for a, s in per_agent.items():
        g = max(1, s["games"])
        s["win_rate"] = s["wins"] / g
        s["points"] = s["wins"] + 0.5 * s["draws"]
        s["avg_seeds_for"] = s["seeds_for"] / g
        s["avg_seeds_against"] = s["seeds_against"] / g
        s["ms_per_move"] = 1000 * s["time"] / max(1, s["moves"])
        s["nodes_per_move"] = s["nodes"] / max(1, s["moves"]) if s["nodes"] else None

    ranking = sorted(agents, key=lambda a: (-per_agent[a]["points"],
                                            -(per_agent[a]["seeds_for"] - per_agent[a]["seeds_against"])))
    return {"duels": duels, "per_agent": per_agent, "ranking": ranking}


# ─────────────────────────────────────────────────────────────────────────────
# Rapports
# ─────────────────────────────────────────────────────────────────────────────


def pct(x: float) -> str:
    return f"{100 * x:.0f} %"


def build_markdown(cfg: dict, agg: dict, agree: Optional[dict], elapsed: float) -> str:
    pa, duels, agents = agg["per_agent"], agg["duels"], cfg["agents"]
    L = []
    L.append("# Benchmark des agents AwaleAI\n")
    L.append(f"_Généré le {cfg['date']} — durée {elapsed:.0f} s_\n")
    L.append("## Protocole\n")
    L.append(f"- **{cfg['games']} parties par duel**, tournoi toutes-rondes "
             f"({len(duels)} duels, {cfg['games'] * len(duels)} parties).")
    L.append(f"- Profondeur de recherche : Minimax = {cfg['depths']['minimax']}, "
             f"Alpha-Bêta = {cfg['depths']['alphabeta']} ; Q-Learning glouton (sans exploration).")
    L.append(f"- Ouvertures : {cfg['opening_plies']} demi-coups aléatoires, chaque ouverture "
             "jouée deux fois en inversant les couleurs (chaque agent commence la moitié des parties).")
    L.append(f"- Nul si répétition de position ou plus de {cfg['max_plies']} demi-coups. "
             f"Graine aléatoire : {cfg['seed']}.\n")

    L.append("## Classement général\n")
    L.append("| Rang | Agent | Victoires | Nuls | Défaites | Taux de victoire | "
             "Graines moy. (pour–contre) | Temps / coup | Nœuds / coup |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for i, a in enumerate(agg["ranking"], 1):
        s = pa[a]
        nodes = f"{s['nodes_per_move']:.0f}" if s["nodes_per_move"] else "—"
        L.append(f"| {i} | **{LABELS[a]}** | {s['wins']} | {s['draws']} | {s['losses']} | "
                 f"{pct(s['win_rate'])} | {s['avg_seeds_for']:.1f} – {s['avg_seeds_against']:.1f} | "
                 f"{s['ms_per_move']:.2f} ms | {nodes} |")
    L.append("")

    L.append("## Matrice des taux de victoire (ligne contre colonne)\n")
    L.append("| | " + " | ".join(LABELS[a] for a in agents) + " |")
    L.append("|---|" + "---|" * len(agents))
    for r in agents:
        row = [f"**{LABELS[r]}**"]
        for c in agents:
            if r == c:
                row.append("—")
                continue
            d = duels.get(f"{r}|{c}") or duels.get(f"{c}|{r}")
            if d is None:
                row.append("")
                continue
            w = d["wins_a"] if d["a"] == r else d["wins_b"]
            row.append(f"{pct(w / d['games'])} ({w}/{d['games']})")
        L.append("| " + " | ".join(row) + " |")
    L.append("")

    L.append("## Détail des duels\n")
    L.append("| Duel | Score (V–N–D) | Graines moy. | Coups moy. | Fin de partie "
             "(score / blocage / répét. / limite) | Temps / coup |")
    L.append("|---|---|---|---|---|---|")
    for d in duels.values():
        er = d["end_reasons"]
        L.append(f"| {LABELS[d['a']]} vs {LABELS[d['b']]} | {d['wins_a']}–{d['draws']}–{d['wins_b']} | "
                 f"{d['avg_seeds_a']:.1f} – {d['avg_seeds_b']:.1f} | {d['avg_plies']:.0f} | "
                 f"{er['score']} / {er['blocage']} / {er['repetition']} / {er['limite']} | "
                 f"{d['ms_per_move_a']:.2f} ms – {d['ms_per_move_b']:.2f} ms |")
    L.append("")

    if agree:
        L.append(f"## Minimax vs Alpha-Bêta à profondeur égale ({agree['depth']})\n")
        L.append(f"Sur **{agree['positions']} positions** variées, chaque algorithme choisit un coup :\n")
        L.append("| Mesure | Minimax | Alpha-Bêta |")
        L.append("|---|---|---|")
        L.append(f"| Nœuds explorés (moyenne) | {agree['nodes_mm']:.0f} | {agree['nodes_ab']:.0f} |")
        L.append(f"| Temps par coup (moyenne) | {agree['ms_mm']:.2f} ms | {agree['ms_ab']:.2f} ms |")
        L.append(f"\n- Coup d'Alpha-Bêta **optimal au sens de Minimax** (même valeur que le meilleur coup "
                 f"Minimax) : **{pct(agree['ab_optimal_rate'])}** des positions.")
        L.append(f"- Coup strictement identique : **{pct(agree['same_rate'])}** des positions "
                 f"(**{pct(agree['same_rate_no_ties'])}** hors égalités ; {pct(agree['tie_rate'])} des positions "
                 "ont plusieurs coups de même valeur, que Minimax départage au hasard).")
        L.append(f"- Alpha-Bêta explore **{pct(1 - agree['nodes_ab'] / max(1, agree['nodes_mm']))} de nœuds en moins** "
                 f"et est **{agree['ms_mm'] / max(1e-9, agree['ms_ab']):.1f}× plus rapide**.")
        L.append("\n> Les deux agents utilisent la même fonction d'évaluation "
                 "(`agents/heuristic/heuristic.py`) : Alpha-Bêta n'est qu'une optimisation de Minimax.\n")

    L.append("![Taux de victoire](winrate.svg)\n")
    return "\n".join(L)


def build_svg(agg: dict) -> str:
    """Histogramme empilé victoires / nuls / défaites (SVG autonome)."""
    pa, ranking = agg["per_agent"], agg["ranking"]
    W, bar_h, gap, left, top = 720, 46, 22, 130, 60
    H = top + len(ranking) * (bar_h + gap) + 50
    width = W - left - 40
    colors = {"wins": "#2e9d5b", "draws": "#c9a227", "losses": "#c0473a"}
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
           f'font-family="Segoe UI, Arial, sans-serif">',
           f'<rect width="{W}" height="{H}" fill="#fffaf2"/>',
           f'<text x="{W/2}" y="34" text-anchor="middle" font-size="20" font-weight="bold" '
           f'fill="#3b2a1a">Benchmark AwaleAI — résultats cumulés</text>']
    for i, a in enumerate(ranking):
        s = pa[a]
        y = top + i * (bar_h + gap)
        out.append(f'<text x="{left - 12}" y="{y + bar_h/2 + 6}" text-anchor="end" '
                   f'font-size="16" fill="#3b2a1a">{LABELS[a]}</text>')
        x = left
        for k in ("wins", "draws", "losses"):
            w = width * s[k] / max(1, s["games"])
            if w > 0:
                out.append(f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{bar_h}" fill="{colors[k]}"/>')
                if w > 34:
                    out.append(f'<text x="{x + w/2:.1f}" y="{y + bar_h/2 + 5}" text-anchor="middle" '
                               f'font-size="14" fill="white">{s[k]}</text>')
            x += w
        out.append(f'<text x="{left + width + 6}" y="{y + bar_h/2 + 5}" font-size="13" '
                   f'fill="#3b2a1a">{pct(s["win_rate"])}</text>')
    ly = H - 22
    for j, (k, lab) in enumerate((("wins", "Victoires"), ("draws", "Nuls"), ("losses", "Défaites"))):
        lx = left + j * 150
        out.append(f'<rect x="{lx}" y="{ly - 12}" width="14" height="14" fill="{colors[k]}"/>')
        out.append(f'<text x="{lx + 20}" y="{ly}" font-size="14" fill="#3b2a1a">{lab}</text>')
    out.append("</svg>")
    return "\n".join(out)


def print_summary(agg: dict, agree: Optional[dict]) -> None:
    pa = agg["per_agent"]
    print("\n" + "=" * 78)
    print(f"{'Agent':<12}{'V':>5}{'N':>5}{'D':>5}{'Taux V':>9}{'Graines':>14}{'ms/coup':>10}{'nœuds/coup':>13}")
    print("-" * 78)
    for a in agg["ranking"]:
        s = pa[a]
        nodes = f"{s['nodes_per_move']:.0f}" if s["nodes_per_move"] else "-"
        print(f"{LABELS[a]:<12}{s['wins']:>5}{s['draws']:>5}{s['losses']:>5}{pct(s['win_rate']):>9}"
              f"{s['avg_seeds_for']:>7.1f}-{s['avg_seeds_against']:<6.1f}{s['ms_per_move']:>10.2f}{nodes:>13}")
    print("=" * 78)
    for d in agg["duels"].values():
        print(f"  {LABELS[d['a']]:>10} {d['wins_a']:>2} – {d['draws']:>2} – {d['wins_b']:<2} {LABELS[d['b']]}")
    if agree:
        print(f"\nMinimax vs Alpha-Bêta (prof. {agree['depth']}, {agree['positions']} positions) : "
              f"coup AB optimal {pct(agree['ab_optimal_rate'])}, même coup {pct(agree['same_rate'])} "
              f"({pct(agree['same_rate_no_ties'])} hors égalités), nœuds {agree['nodes_mm']:.0f} vs {agree['nodes_ab']:.0f}, "
              f"{agree['ms_mm']:.2f} ms vs {agree['ms_ab']:.2f} ms")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser(description="Benchmark des agents AwaleAI")
    ap.add_argument("--games", type=int, default=50, help="parties par duel (pair, défaut 50)")
    ap.add_argument("--depth", type=int, default=4, help="profondeur commune Minimax / Alpha-Bêta")
    ap.add_argument("--minimax-depth", type=int, help="profondeur Minimax (prioritaire sur --depth)")
    ap.add_argument("--alphabeta-depth", type=int, help="profondeur Alpha-Bêta (prioritaire sur --depth)")
    ap.add_argument("--agents", nargs="+", default=AGENT_ORDER, choices=AGENT_ORDER)
    ap.add_argument("--opening-plies", type=int, default=2, help="demi-coups aléatoires d'ouverture")
    ap.add_argument("--max-plies", type=int, default=400)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--agreement-positions", type=int, default=200,
                    help="positions pour comparer Minimax/Alpha-Bêta (0 = désactivé)")
    ap.add_argument("--out", default=os.path.join("benchmark", "results"))
    args = ap.parse_args()

    if args.games % 2:
        ap.error("--games doit être pair (chaque ouverture est jouée avec les deux couleurs)")

    depths = {"minimax": args.minimax_depth or args.depth,
              "alphabeta": args.alphabeta_depth or args.depth}
    rng = random.Random(args.seed)
    openings = [make_opening(rng, args.opening_plies) for _ in range(args.games // 2)]

    jobs = []
    for a, b in itertools.combinations(args.agents, 2):
        for oid, op in enumerate(openings):
            for a_is_p1 in (True, False):
                jobs.append({"a": a, "b": b, "a_is_p1": a_is_p1, "opening": op, "opening_id": oid,
                             "depths": depths, "max_plies": args.max_plies,
                             "seed": rng.randrange(2**31)})

    print(f"Benchmark : {len(jobs)} parties ({args.games} par duel), profondeurs {depths}, "
          f"{args.workers} processus…")
    t0 = time.perf_counter()
    results: list[GameResult] = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        for i, r in enumerate(ex.map(run_match, jobs, chunksize=1), 1):
            results.append(r)
            if i % 25 == 0 or i == len(jobs):
                print(f"  {i}/{len(jobs)} parties terminées ({time.perf_counter() - t0:.0f} s)")

        agree = None
        if args.agreement_positions and {"minimax", "alphabeta"} <= set(args.agents):
            d = min(depths.values())
            pos = sample_positions(random.Random(args.seed + 1), args.agreement_positions)
            ag = list(ex.map(agreement_job, [{"moves": m, "depth": d} for m in pos], chunksize=4))
            agree = {
                "depth": d, "positions": len(ag),
                "same_rate": sum(x["same"] for x in ag) / len(ag),
                "ab_optimal_rate": sum(x["ab_optimal"] for x in ag) / len(ag),
                "mm_optimal_rate": sum(x["mm_optimal"] for x in ag) / len(ag),
                "tie_rate": sum(x["ties"] for x in ag) / len(ag),
                "same_rate_no_ties": (sum(x["same"] for x in ag if not x["ties"])
                                      / max(1, sum(not x["ties"] for x in ag))),
                "nodes_mm": statistics.mean(x["nodes_mm"] for x in ag),
                "nodes_ab": statistics.mean(x["nodes_ab"] for x in ag),
                "ms_mm": 1000 * statistics.mean(x["time_mm"] for x in ag),
                "ms_ab": 1000 * statistics.mean(x["time_ab"] for x in ag),
            }
    elapsed = time.perf_counter() - t0

    agg = aggregate(results, args.agents)
    cfg = {"date": datetime.now().strftime("%Y-%m-%d %H:%M"), "games": args.games,
           "depths": depths, "agents": args.agents, "opening_plies": args.opening_plies,
           "max_plies": args.max_plies, "seed": args.seed}

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "results.json"), "w", encoding="utf-8") as f:
        json.dump({"config": cfg, "elapsed_s": elapsed, **agg, "minimax_vs_alphabeta": agree},
                  f, ensure_ascii=False, indent=2)
    with open(os.path.join(args.out, "games.csv"), "w", newline="", encoding="utf-8") as f:
        fields = list(asdict(results[0]).keys())
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in results:
            row = asdict(r)
            row["opening"] = " ".join(map(str, row["opening"]))
            w.writerow(row)
    with open(os.path.join(args.out, "RESULTS.md"), "w", encoding="utf-8") as f:
        f.write(build_markdown(cfg, agg, agree, elapsed))
    with open(os.path.join(args.out, "winrate.svg"), "w", encoding="utf-8") as f:
        f.write(build_svg(agg))

    print_summary(agg, agree)
    print(f"\nRésultats écrits dans {args.out}/ (RESULTS.md, results.json, games.csv, winrate.svg)")


if __name__ == "__main__":
    main()
