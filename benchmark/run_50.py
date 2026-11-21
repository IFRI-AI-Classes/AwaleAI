"""Exactly 50 measured games, a checked CSV and a single Matplotlib PNG."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import itertools
import json
import math
from pathlib import Path
import platform
import random
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agents.difficulty import choose_move_by_agent, effective_depth
from awale.ai.qlearning import QLearningAgent
from engine.game import Game

AGENTS = ("random", "minimax", "alphabeta", "qlearning")
LABELS = {"random": "Random", "minimax": "Minimax", "alphabeta": "Alpha-Bêta", "qlearning": "Q-Learning"}
ENDINGS = {"score", "blocage", "repetition", "limite"}
FIELDS = [
    "game_id", "duel", "pair_id", "leg", "agent_a", "agent_b", "player1", "player2",
    "winner", "end_reason", "plies", "agent_plies", "duration_seconds", "seed", "opening_seed",
    "initial_position", "opening_moves", "moves", "final_board", "final_raw_scores", "final_scores",
    "decision_seconds_player1", "decision_seconds_player2", "position_trace_sha256",
]
JSON_FIELDS = ("initial_position", "opening_moves", "moves", "final_board", "final_raw_scores", "final_scores")
INT_FIELDS = ("leg", "plies", "agent_plies", "seed", "opening_seed")
FLOAT_FIELDS = ("duration_seconds", "decision_seconds_player1", "decision_seconds_player2")
SOURCES = (
    "engine/board.py", "engine/rules.py", "engine/game.py", "agents/difficulty.py",
    "agents/random/random_agent.py", "agents/minimax/minimax.py",
    "agents/alpha_beta/elagage.py", "agents/heuristic/heuristic.py", "awale/ai/qlearning.py",
)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_config(config):
    require(config["total_games"] == 50 and type(config["total_games"]) is int, "Cette expérience exige exactement 50 parties.")
    require(tuple(config["agents"]) == AGENTS, "Les quatre agents et leur ordre doivent être conservés.")
    extras = [tuple(pair) for pair in config["extra_duels"]]
    duels = list(itertools.combinations(AGENTS, 2))
    require(len(extras) == 2 and len(set(extras)) == 2 and all(p in duels for p in extras), "Deux duels supplémentaires distincts sont requis.")
    require(Counter(itertools.chain.from_iterable(extras)) == Counter(AGENTS), "Chaque agent doit recevoir une seule partie supplémentaire.")
    require(type(config["master_seed"]) is int, "La graine doit être un entier.")
    opening, limit = config["opening_plies"], config["max_plies"]
    require(type(opening) is int and opening >= 0 and opening % 2 == 0, "L'ouverture exige un nombre pair de coups, positif ou nul.")
    require(type(limit) is int and limit > opening, "La limite doit dépasser la longueur de l'ouverture.")
    for agent in ("minimax", "alphabeta"):
        effective_depth(agent, config["depths"][agent])
    q = config["qlearning"]
    require(q["checkpoint"] == "best" and q["greedy"] is True and q["training"] is False, "Q-Learning doit utiliser best en exploitation, sans entraînement.")
    require(len(q["sha256"]) == 64, "Une empreinte du checkpoint est requise.")
    chart = config["chart"]
    require((chart["width_inches"], chart["height_inches"], chart["dpi"]) == (16, 9, 300), "Le graphique doit être en 16:9 à 300 dpi.")
    require(Path(chart["filename"]).name == chart["filename"] and chart["filename"].endswith(".png"), "Un seul nom de fichier PNG est autorisé.")
    require(chr(0x2014) not in canonical(config), "La configuration contient un tiret cadratin interdit.")


def make_schedule(config):
    """8 games per duel, plus 1 for two disjoint duels: 25 per agent."""
    check_config(config)
    duels = list(itertools.combinations(AGENTS, 2))
    extras = {tuple(pair) for pair in config["extra_duels"]}
    rng = random.Random(config["master_seed"])
    pair_seeds = {}
    for a, b in duels:
        for pair_index in range(5 if (a, b) in extras else 4):
            pair_seeds[(a, b, pair_index)] = (rng.randrange(2**31), rng.randrange(2**31))
    schedule = []
    # Interleave duels; reverse seats on each successive leg of a duel.
    for leg_index in range(9):
        for a, b in duels:
            if leg_index >= 8 + ((a, b) in extras):
                continue
            opening_seed, seed = pair_seeds[(a, b, leg_index // 2)]
            p1, p2 = (a, b) if leg_index % 2 == 0 else (b, a)
            schedule.append({
                "game_id": f"G{len(schedule) + 1:03d}", "duel": f"{a}:{b}",
                "pair_id": f"{a}:{b}:{leg_index // 2 + 1}", "leg": leg_index % 2 + 1,
                "agent_a": a, "agent_b": b, "player1": p1, "player2": p2,
                "seed": seed, "opening_seed": opening_seed,
            })
    require(len(schedule) == 50, "Le calendrier ne contient pas 50 parties.")
    return schedule


def state_snapshot(game):
    return {"board": list(game.board.holes), "scores": [game.score_p1, game.score_p2],
            "current_player": game.current_player, "plies": game.plies, "max_plies": game.max_plies}


def check_conservation(game):
    require(len(game.board.holes) == 12 and all(type(x) is int and x >= 0 for x in game.board.holes), "Plateau invalide.")
    require(sum(game.board.holes) + game.score_p1 + game.score_p2 == 48, "Conservation des 48 graines violée.")


def add_trace(trace, game):
    trace.update((canonical(state_snapshot(game)) + "\n").encode("utf-8"))


def play_one(job, config, q_agent):
    """One actual game; every choice is validated by the unchanged engine."""
    started = time.perf_counter()
    game = Game(max_plies=config["max_plies"])
    trace = hashlib.sha256()
    add_trace(trace, game)
    opening_rng = random.Random(job["opening_seed"])
    moves = []
    for _ in range(config["opening_plies"]):
        require(not game.is_game_over(), "Ouverture terminale : arrêter l'expérience, sans remplacer une partie.")
        move = opening_rng.choice(game.get_valid_moves())
        require(game.play_move(move), "Coup d'ouverture refusé.")
        moves.append(move)
        check_conservation(game)
        add_trace(trace, game)
    require(not game.is_game_over(), "L'ouverture ne doit pas terminer la partie.")
    initial = state_snapshot(game)
    opening_moves = list(moves)
    random.seed(job["seed"])
    decision_times = [0.0, 0.0]
    while not game.is_game_over():
        player = game.current_player
        agent = job[f"player{player}"]
        legal = game.get_valid_moves()
        decision_start = time.perf_counter()
        if agent == "qlearning":
            move = q_agent.choose_move(game, greedy=True)
        else:
            move, _ = choose_move_by_agent(game, agent, config["depths"].get(agent))
        decision_times[player - 1] += time.perf_counter() - decision_start
        require(type(move) is int and move in legal, f"Coup illégal : {job['game_id']}, {agent}, {move}.")
        require(game.play_move(move), "Le moteur a refusé un coup validé.")
        moves.append(move)
        check_conservation(game)
        require(game.plies <= config["max_plies"], "La partie a dépassé sa limite.")
        add_trace(trace, game)
    elapsed = time.perf_counter() - started
    reason = game.end_reason()
    require(reason in ENDINGS, "Fin de partie non reconnue.")
    winner_player = game.get_winner()
    require(winner_player in (None, 1, 2), "Gagnant invalide.")
    return {
        **job, "winner": job[f"player{winner_player}"] if winner_player else "draw", "end_reason": reason,
        "plies": game.plies, "agent_plies": game.plies - len(opening_moves), "duration_seconds": elapsed,
        "initial_position": initial, "opening_moves": opening_moves, "moves": moves,
        "final_board": list(game.board.holes), "final_raw_scores": [game.score_p1, game.score_p2],
        "final_scores": list(game.final_scores()), "decision_seconds_player1": decision_times[0],
        "decision_seconds_player2": decision_times[1], "position_trace_sha256": trace.hexdigest(),
    }


def write_row(writer, row):
    writer.writerow({key: canonical(row[key]) if key in JSON_FIELDS else row[key] for key in FIELDS})


def read_csv(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == FIELDS, "Colonnes CSV inattendues.")
        rows = list(reader)
    for row in rows:
        for key in JSON_FIELDS:
            row[key] = json.loads(row[key])
        for key in INT_FIELDS:
            row[key] = int(row[key])
        for key in FLOAT_FIELDS:
            row[key] = float(row[key])
    return rows


def validate_rows(rows, config):
    """Replay recorded moves only; does not ask agents to play more games."""
    schedule = make_schedule(config)
    require(len(rows) == len(schedule) == 50, "Le CSV doit contenir exactement 50 parties.")
    require(len({r["game_id"] for r in rows}) == 50, "Identifiants de parties dupliqués.")
    paired = {}
    for row, job in zip(rows, schedule):
        require(all(row[k] == v for k, v in job.items()), f"Calendrier ou graine incohérents : {row['game_id']}.")
        for key in FLOAT_FIELDS:
            require(math.isfinite(row[key]) and row[key] >= 0, "Temps invalide dans le CSV.")
        require(row["duration_seconds"] > 0, "Une durée doit être mesurée.")
        require(row["winner"] in (row["player1"], row["player2"], "draw"), "Gagnant étranger au duel.")
        require(row["end_reason"] in ENDINGS, "Motif de fin invalide.")
        game = Game(max_plies=config["max_plies"])
        trace = hashlib.sha256()
        add_trace(trace, game)
        require(len(row["opening_moves"]) == config["opening_plies"], "Longueur d'ouverture incohérente.")
        require(row["moves"][:config["opening_plies"]] == row["opening_moves"], "Ouverture absente de la trajectoire.")
        rng = random.Random(row["opening_seed"])
        for index, move in enumerate(row["moves"]):
            require(type(move) is int and move in game.get_valid_moves(), "La trajectoire contient un coup illégal ou postérieur à la fin.")
            if index < config["opening_plies"]:
                require(move == rng.choice(game.get_valid_moves()), "L'ouverture ne correspond pas à sa graine.")
            require(game.play_move(move), "Trajectoire refusée par le moteur.")
            check_conservation(game)
            add_trace(trace, game)
            if index + 1 == config["opening_plies"]:
                require(state_snapshot(game) == row["initial_position"], "Position initiale incohérente.")
        if config["opening_plies"] == 0:
            require(row["initial_position"] == state_snapshot(Game(max_plies=config["max_plies"])), "Position standard incohérente.")
        require(game.is_game_over() and not game.get_valid_moves(), "Partie non terminée.")
        winner = game.get_winner()
        winner_agent = row[f"player{winner}"] if winner else "draw"
        require(row["winner"] == winner_agent and row["end_reason"] == game.end_reason(), "Résultat incompatible avec le moteur.")
        require(row["plies"] == len(row["moves"]) == game.plies, "Nombre de coups incohérent.")
        require(row["agent_plies"] == game.plies - config["opening_plies"], "Nombre de coups des agents incohérent.")
        require(row["final_board"] == game.board.holes and row["final_raw_scores"] == [game.score_p1, game.score_p2], "État final incohérent.")
        require(row["final_scores"] == list(game.final_scores()), "Scores finaux incohérents.")
        require(row["position_trace_sha256"] == trace.hexdigest(), "Empreinte de trajectoire incohérente.")
        previous = paired.setdefault(row["pair_id"], row)
        require(previous["initial_position"] == row["initial_position"] and previous["opening_moves"] == row["opening_moves"], "Ouvertures aller-retour différentes.")
    stats = aggregate(rows)
    require(all(s["games"] == 25 and abs(s["first_player_games"] - s["second_player_games"]) == 1 for s in stats.values()), "Répartition par agent incorrecte.")
    decisive = sum(r["winner"] != "draw" for r in rows)
    draws = 50 - decisive
    require(sum(s["wins"] for s in stats.values()) == sum(s["losses"] for s in stats.values()) == decisive, "Comptes de victoires/défaites incohérents.")
    require(sum(s["draws"] for s in stats.values()) == 2 * draws, "Comptes de nuls incohérents.")
    require(sum(s["games"] for s in stats.values()) == 100, "Les 50 parties doivent donner 100 participations.")
    return stats


def aggregate(rows):
    stats = {a: {"wins": 0, "draws": 0, "losses": 0, "games": 0, "first_player_games": 0,
                 "second_player_games": 0, "decision_seconds": 0.0, "agent_moves": 0} for a in AGENTS}
    for row in rows:
        for seat in (1, 2):
            agent = row[f"player{seat}"]
            s = stats[agent]
            s["games"] += 1
            s["first_player_games" if seat == 1 else "second_player_games"] += 1
            outcome = "draws" if row["winner"] == "draw" else "wins" if row["winner"] == agent else "losses"
            s[outcome] += 1
            s["decision_seconds"] += row[f"decision_seconds_player{seat}"]
            # Opening length is even, so the first agent move is played by player 1.
            s["agent_moves"] += (row["agent_plies"] + (1 if seat == 1 else 0)) // 2
    for s in stats.values():
        require(s["games"] == s["wins"] + s["draws"] + s["losses"], "Bilan individuel incohérent.")
        s["win_rate_denominator"] = s["games"]
        s["win_rate"] = s["wins"] / s["games"] if s["games"] else 0.0
        s["mean_decision_ms"] = 1000 * s["decision_seconds"] / s["agent_moves"] if s["agent_moves"] else None
    return stats


def chart_series(stats):
    return {a: {key: stats[a][key] for key in ("wins", "draws", "losses", "games")} for a in AGENTS}


def render_chart(stats, config, destination):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    colors = config["chart"]["colors"]
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 16, "axes.labelcolor": "#173B65", "text.color": "#173B65"})
    fig, ax = plt.subplots(figsize=(16, 9), dpi=300)
    fig.patch.set_facecolor("#F7FAFE")
    ax.set_facecolor("#F7FAFE")
    fig.subplots_adjust(left=.085, right=.965, bottom=.26, top=.76)
    fig.text(.085, .925, config["chart"]["title"], fontsize=30, weight="bold")
    depth = config["depths"]
    fig.text(.085, .867, f"Minimax : profondeur {depth['minimax']}  •  Alpha-Bêta : profondeur {depth['alphabeta']}  •  Q-Learning : best, sans entraînement", fontsize=16, color="#526B86")
    positions = list(range(4))
    bottom = [0] * 4
    for key, label in (("wins", "Victoires"), ("draws", "Matchs nuls"), ("losses", "Défaites")):
        values = [stats[a][key] for a in AGENTS]
        bars = ax.bar(positions, values, bottom=bottom, width=.52, color=colors[key], label=label, linewidth=0)
        for i, (bar, value) in enumerate(zip(bars, values)):
            require(bar.get_height() == value and bar.get_y() == bottom[i], "Le graphique ne correspond pas aux données.")
            if value:
                ax.text(bar.get_x() + bar.get_width()/2, bottom[i] + value/2, str(value),
                        ha="center", va="center", fontsize=13 if value == 1 else 17 if value == 2 else 21,
                        weight="bold", color="#173B65" if key == "draws" else "white")
        bottom = [b + v for b, v in zip(bottom, values)]
    require(bottom == [stats[a]["games"] for a in AGENTS], "Hauteurs totales incohérentes.")
    ax.set_ylim(0, 29)
    ax.set_xlim(-.7, 3.7)
    ax.set_ylabel("Nombre de parties", fontsize=18, labelpad=16)
    ax.set_xticks(positions, [LABELS[a] for a in AGENTS], fontsize=20, weight="bold")
    ax.tick_params(axis="x", length=0, pad=16)
    ax.tick_params(axis="y", length=0, labelsize=15, colors="#526B86")
    ax.yaxis.set_major_locator(MaxNLocator(integer=True, nbins=6))
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#D9E4F0", linewidth=.8)
    for spine in ax.spines.values():
        spine.set_visible(False)
    for i, a in enumerate(AGENTS):
        s = stats[a]
        rate = f"{100*s['win_rate']:.0f} %"
        ax.text(i, s["games"] + .65, f"{rate} de victoires", ha="center", fontsize=16, weight="bold")
        # Also show zero values, whose stacked segment has no visible height.
        ax.text(i, -.16, f"V {s['wins']}  •  N {s['draws']}  •  D {s['losses']}", transform=ax.get_xaxis_transform(), ha="center", fontsize=14, color="#526B86")
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.015), ncol=3, frameon=False, fontsize=17, handlelength=1.25, columnspacing=2)
    fig.text(.085, .095, "50 parties uniques  •  25 parties par agent  •  Taux de victoire = victoires / 25 (matchs nuls inclus)", fontsize=15, color="#173B65")
    fig.text(.085, .048, "Départs alternés, ouvertures appariées et graines fixes. Comparaison exploratoire sur un petit échantillon.", fontsize=13, color="#526B86")
    payload = canonical(chart_series(stats))
    fig.savefig(destination, dpi=300, facecolor=fig.get_facecolor(),
                metadata={"Title": config["chart"]["title"], "Description": payload, "Software": f"Matplotlib {matplotlib.__version__}"})
    plt.close(fig)


def verify_outputs(output, config, metadata):
    from PIL import Image
    rows = read_csv(output / "games.csv")
    stats = validate_rows(rows, config)
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    require(summary["agents"] == stats, "Résumé différent de l'agrégation CSV.")
    require(summary["unique_games"] == 50, "Résumé de taille incorrecte.")
    require(summary["csv_sha256"] == digest(output / "games.csv"), "Empreinte CSV différente du résumé.")
    for source, expected in metadata["source_sha256"].items():
        require(digest(ROOT / source) == expected, f"Source modifiée depuis l'expérience : {source}.")
    for model, expected in metadata["model_files_sha256"].items():
        require(digest(ROOT / model) == expected, f"Modèle historique modifié : {model}.")
    image_path = output / config["chart"]["filename"]
    with Image.open(image_path) as image:
        require(image.format == "PNG" and image.size == (4800, 2700), "Format du PNG incorrect.")
        require(json.loads(image.info["Description"]) == chart_series(stats), "Données du PNG différentes du CSV.")
    require(len(list(output.glob("*.png"))) == 1, "Un seul graphique final PNG est autorisé.")
    verification = {
        "unique_games": 50, "agent_participations": 100, "all_games_terminal": True,
        "all_recorded_moves_legal": True, "seed_conservation_checked_after_every_move": True,
        "paired_openings_identical": True, "csv_summary_chart_agree": True,
        "sources_and_models_unchanged": True, "chart_dimensions": [4800, 2700],
        "csv_sha256": digest(output / "games.csv"), "png_sha256": digest(image_path),
    }
    write_json(output / "verification.json", verification)
    return stats


def report_markdown(rows, stats, config, metadata):
    lines = ["# Benchmark des agents IA : 50 parties", "", "Résultats mesurés localement, sans entraînement ni modification des agents.", "",
             "| Agent | Victoires | Matchs nuls | Défaites | Parties | Taux de victoire | Premier / second joueur |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for a in AGENTS:
        s = stats[a]
        lines.append(f"| {LABELS[a]} | {s['wins']} | {s['draws']} | {s['losses']} | {s['games']} | {100*s['win_rate']:.1f} % | {s['first_player_games']} / {s['second_player_games']} |")
    lines += ["", "Le dénominateur est le nombre total de parties disputées par l'agent, soit 25, matchs nuls et défaites inclus.", "",
              "## Protocole", "", f"Graine maîtresse : `{config['master_seed']}`. Minimax et Alpha-Bêta : profondeur `{config['depths']['minimax']}` et `{config['depths']['alphabeta']}`, en demi-coups.",
              f"Ouvertures : {config['opening_plies']} coups légaux choisis avec une graine fixe, depuis le plateau standard de 4 graines par case. Même ouverture et même graine de décisions dans chaque aller-retour, avec échange des joueurs.",
              f"Limite moteur : {config['max_plies']} coups, ouverture incluse. Les coups automatiques d'ouverture ne sont pas attribués aux agents.", "",
              "| Duel | Parties |", "| --- | ---: |"]
    for duel, number in Counter(r["duel"] for r in rows).items():
        a, b = duel.split(":")
        lines.append(f"| {LABELS[a]} / {LABELS[b]} | {number} |")
    reasons = Counter(r["end_reason"] for r in rows)
    total_seconds = sum(r["duration_seconds"] for r in rows)
    lines += ["", f"Durée cumulée mesurée des parties : {total_seconds:.3f} s. Le chargement du modèle, la vérification des trajectoires et la production du PNG sont exclus.",
              f"Motifs de fin : `{canonical(dict(reasons))}`.", "", "## Q-Learning", "",
              f"Checkpoint chargé exactement : `{metadata['qlearning']['path']}`. SHA-256 : `{metadata['qlearning']['sha256']}`.",
              f"États de la table : {metadata['qlearning']['states']}. Politique d'exploitation (`greedy=True`), aucune mise à jour ou sauvegarde de la Q-table.", "",
              "## Vérifications", "", "Les 50 lignes du CSV sont relues et leurs coups rejoués avec le moteur, sans solliciter les agents et sans ajouter de nouvelles confrontations.",
              "Les graines, ouvertures, positions, scores, gagnants, fins et nombres de coups sont vérifiés. Les comptes individuels donnent 100 participations pour 50 parties uniques. Chaque victoire correspond à une défaite ; chaque match nul figure dans le bilan de deux agents.",
              "Les valeurs des rectangles Matplotlib sont contrôlées avant export. Les données intégrées au PNG, le résumé JSON et l'agrégation indépendante du CSV doivent être identiques. Voir `verification.json`.", "",
              "## Limites", "", "50 parties constituent une première comparaison, pas une preuve définitive de supériorité. Les 24 aller-retours sont appariés : ils ne constituent pas 48 observations indépendantes. Deux parties supplémentaires ne sont pas appariées ; elles permettent 25 parties par agent.",
              "Ces résultats dépendent de la profondeur choisie, du checkpoint Q-Learning, des ouvertures, des adversaires et de la variante du moteur. Minimax et Alpha-Bêta utilisent le même horizon et la même heuristique ; leurs égalités peuvent être départagées différemment.",
              "Le moteur permet l'affamement si tous les coups l'imposent ; ce benchmark suit cette variante locale et ne prétend pas certifier toutes les variantes officielles. Les répétitions et la limite de coups donnent un match nul, même avec des scores différents.",
              "Le taux observé ne démontre pas un progrès d'apprentissage du Q-Learning. Les temps dépendent de la machine et ne sont pas reproductibles à l'identique ; les graines, coups et résultats sont reproductibles avec les mêmes sources, versions et modèle.", "",
              "## Artefacts", "", "`games.csv`, `summary.json`, `run_metadata.json`, `verification.json` et un seul graphique `benchmark_50.png` (4800 × 2700, 16:9, 300 dpi).", ""]
    return "\n".join(lines)


def run(config, output):
    check_config(config)
    schedule = make_schedule(config)
    # Refuse accidental replacement of measured results.
    require(not output.exists() or not any(output.iterdir()), "Le dossier de résultats doit être vide. Utilisez --output pour une nouvelle exécution.")
    model = (ROOT / config["qlearning"]["path"]).resolve()
    require(model.is_file() and digest(model) == config["qlearning"]["sha256"], "Checkpoint absent ou empreinte différente de la configuration.")
    # The agent's loader normally permits fallback; make that impossible for this experiment.
    q_agent = QLearningAgent(checkpoint="best", model_dir=model.parent)
    require(q_agent.loaded_path is not None and Path(q_agent.loaded_path).resolve() == model, "Le checkpoint demandé n'a pas été chargé exactement.")
    table_before = hashlib.sha256(canonical(q_agent.q_table).encode("utf-8")).hexdigest()
    model_hashes = {f"models/{name}": digest(ROOT / "models" / name) for name in ("q_table_best.json", "q_table_latest.json")}
    metadata = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(), "python": sys.version, "platform": platform.platform(),
        "config": config, "config_sha256": hashlib.sha256(canonical(config).encode("utf-8")).hexdigest(),
        "source_sha256": {source: digest(ROOT / source) for source in SOURCES}, "model_files_sha256": model_hashes,
        "benchmark_script_sha256": digest(Path(__file__)),
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "git_branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
        "qlearning": {"path": config["qlearning"]["path"], "sha256": digest(model), "states": len(q_agent.q_table),
                      "greedy": True, "training": False, "loaded_alpha": q_agent.alpha, "loaded_gamma": q_agent.gamma,
                      "loaded_epsilon": q_agent.epsilon, "epsilon_applied_to_decisions": 0.0,
                      "total_episodes_in_checkpoint": q_agent.total_episodes},
        "duration_definition": "Wall time from game creation and opening to terminal state, including decision validation and move trace hashing; excludes model load and post-run verification.",
        "rng_protocol": "Independent opening RNG; Python global random reset to the recorded seed before each game's agent decisions; sequential execution.",
    }
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "run_metadata.json", metadata)
    rows = []
    with (output / "games.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        for job in schedule:
            row = play_one(job, config, q_agent)
            rows.append(row)
            write_row(writer, row)
            stream.flush()
            print(f"{len(rows):02d}/50 {LABELS[row['player1']]} / {LABELS[row['player2']]} : {LABELS.get(row['winner'], 'Match nul')}, {row['plies']} coups, {row['duration_seconds']:.3f} s", flush=True)
    require(hashlib.sha256(canonical(q_agent.q_table).encode("utf-8")).hexdigest() == table_before, "La Q-table a changé pendant l'expérience.")
    metadata["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    metadata["completed_games"] = len(rows)
    write_json(output / "run_metadata.json", metadata)
    # Aggregate the persisted CSV, not just the in-memory results.
    persisted = read_csv(output / "games.csv")
    stats = validate_rows(persisted, config)
    summary = {"unique_games": 50, "agents": stats, "duels": dict(Counter(r["duel"] for r in persisted)),
               "end_reasons": dict(Counter(r["end_reason"] for r in persisted)), "csv_sha256": digest(output / "games.csv"),
               "total_game_duration_seconds": sum(r["duration_seconds"] for r in persisted)}
    write_json(output / "summary.json", summary)
    render_chart(stats, config, output / config["chart"]["filename"])
    verify_outputs(output, config, metadata)
    (output / "summary.md").write_text(report_markdown(persisted, stats, config, metadata), encoding="utf-8")
    print(f"VERIFIED: 50 parties, 100 participations, CSV/résumé/PNG cohérents. {output}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="50 parties au total, quatre agents, un seul graphique PNG.")
    parser.add_argument("--config", type=Path, default=ROOT / "benchmark/config_50.json")
    parser.add_argument("--output", type=Path, help="Nouveau dossier vide de résultats.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--verify-only", action="store_true", help="Vérifier le CSV, le résumé et le PNG sans faire jouer les agents.")
    mode.add_argument("--render-only", action="store_true", help="Recréer uniquement le PNG depuis le CSV existant, sans rejouer de parties.")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    check_config(config)
    output = (args.output or ROOT / config["output_directory"]).resolve()
    if args.verify_only or args.render_only:
        metadata = json.loads((output / "run_metadata.json").read_text(encoding="utf-8"))
        require(metadata["config"] == config, "La configuration diffère de celle de l'exécution.")
        if args.render_only:
            stats = validate_rows(read_csv(output / "games.csv"), config)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            require(summary["agents"] == stats, "Le résumé doit correspondre au CSV avant export.")
            render_chart(stats, config, output / config["chart"]["filename"])
        verify_outputs(output, config, metadata)
        print("VERIFIED: 50 parties enregistrées, aucune confrontation supplémentaire.")
    else:
        run(config, output)


if __name__ == "__main__":
    main()
