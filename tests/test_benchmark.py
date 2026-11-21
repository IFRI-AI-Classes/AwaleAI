"""Benchmark invariants; fixtures are synthetic and never measured results."""
from collections import Counter
import csv
import io
import json
import unittest

from benchmark import run_50 as bench


def config():
    return json.loads((bench.ROOT / "benchmark/config_50.json").read_text(encoding="utf-8"))


class BenchmarkTests(unittest.TestCase):
    def test_schedule_has_exactly_50_unique_games_and_six_balanced_duels(self):
        jobs = bench.make_schedule(config())
        self.assertEqual(len(jobs), 50)
        self.assertEqual(len({j['game_id'] for j in jobs}), 50)
        counts = Counter(j['duel'] for j in jobs)
        self.assertEqual(sorted(counts.values()), [8, 8, 8, 8, 9, 9])

    def test_each_agent_gets_25_games_and_balanced_seats(self):
        jobs = bench.make_schedule(config())
        for agent in bench.AGENTS:
            p1 = sum(j['player1'] == agent for j in jobs)
            p2 = sum(j['player2'] == agent for j in jobs)
            self.assertEqual(p1 + p2, 25)
            self.assertEqual(abs(p1 - p2), 1)

    def test_paired_games_reverse_players_and_share_both_seeds(self):
        pairs = {}
        for job in bench.make_schedule(config()):
            pairs.setdefault(job['pair_id'], []).append(job)
        self.assertEqual(Counter(len(group) for group in pairs.values()), {2: 24, 1: 2})
        for group in pairs.values():
            if len(group) == 2:
                first, second = group
                self.assertEqual((first['player1'], first['player2']), (second['player2'], second['player1']))
                self.assertEqual(first['seed'], second['seed'])
                self.assertEqual(first['opening_seed'], second['opening_seed'])

    def test_schedule_is_deterministic_and_master_seed_changes_only_randomness(self):
        first = bench.make_schedule(config())
        self.assertEqual(first, bench.make_schedule(config()))
        other = config()
        other['master_seed'] += 1
        second = bench.make_schedule(other)
        self.assertNotEqual([j['seed'] for j in first], [j['seed'] for j in second])
        self.assertEqual([j['player1'] for j in first], [j['player1'] for j in second])

    def test_invalid_total_or_extra_duels_cannot_start_an_experiment(self):
        for size in (0, 49, 51, True):
            invalid = config()
            invalid['total_games'] = size
            with self.assertRaises(ValueError):
                bench.make_schedule(invalid)
        invalid = config()
        invalid['extra_duels'] = [['random', 'minimax'], ['random', 'alphabeta']]
        with self.assertRaises(ValueError):
            bench.make_schedule(invalid)

    def test_win_rate_denominator_includes_draws_and_losses(self):
        # Synthetic fixtures test accounting, not agent performance.
        base = {'agent_plies': 3, 'decision_seconds_player1': .01, 'decision_seconds_player2': .02}
        rows = [dict(base, player1='random', player2='minimax', winner='random'),
                dict(base, player1='alphabeta', player2='random', winner='draw')]
        stats = bench.aggregate(rows)
        self.assertEqual((stats['random']['wins'], stats['random']['draws'], stats['random']['losses']), (1, 1, 0))
        self.assertEqual(stats['random']['win_rate'], .5)
        self.assertEqual(stats['random']['win_rate_denominator'], 2)
        self.assertEqual(stats['minimax']['losses'], 1)
        self.assertEqual(sum(s['games'] for s in stats.values()), 4)
        self.assertEqual(sum(s['wins'] for s in stats.values()), 1)
        self.assertEqual(sum(s['losses'] for s in stats.values()), 1)
        self.assertEqual(sum(s['draws'] for s in stats.values()), 2)

    def test_csv_serializes_initial_position_and_all_moves_losslessly(self):
        job = bench.make_schedule(config())[0]
        row = {**job, **{key: 0 for key in bench.FIELDS if key not in job}}
        row.update({key: [] for key in bench.JSON_FIELDS})
        row['initial_position'] = {'board': [4] * 12, 'scores': [0, 0], 'current_player': 1}
        row['moves'] = [0, 6, 1, 7]
        stream = io.StringIO(newline='')
        writer = csv.DictWriter(stream, fieldnames=bench.FIELDS)
        writer.writeheader()
        bench.write_row(writer, row)
        stream.seek(0)
        decoded = next(csv.DictReader(stream))
        self.assertEqual(json.loads(decoded['initial_position']), row['initial_position'])
        self.assertEqual(json.loads(decoded['moves']), row['moves'])

    def test_incomplete_csv_is_refused_before_trace_replay(self):
        with self.assertRaises(ValueError):
            bench.validate_rows([], config())


if __name__ == '__main__':
    unittest.main()
