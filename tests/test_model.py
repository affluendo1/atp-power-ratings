import unittest

import pandas as pd

from model import MATCH_EVIDENCE_CAP_GAMES, fit_power_ratings_from_df, score_to_games
from generate_site_data import match_win_probability, set_win_probability


class ScoreParsingTests(unittest.TestCase):
    def test_tiebreak_points_are_not_games(self):
        self.assertEqual(score_to_games("6-7(5) 7-5 [10-5]"), (13, 12))

    def test_five_sets_use_conventional_games(self):
        self.assertEqual(score_to_games("6-4 3-6 7-6(4) 4-6 6-3"), (26, 25))


class RatingTests(unittest.TestCase):
    def test_best_of_five_and_best_of_three_fit_together(self):
        rows = pd.DataFrame([
            {"date": "2026-01-01", "winner_id": "a", "loser_id": "b", "winner_name": "A", "loser_name": "B", "score": "6-4 6-4", "status": "completed"},
            {"date": "2026-01-15", "winner_id": "b", "loser_id": "c", "winner_name": "B", "loser_name": "C", "score": "6-4 3-6 7-6(4) 4-6 6-3", "status": "completed"},
            {"date": "2026-02-01", "winner_id": "a", "loser_id": "c", "winner_name": "A", "loser_name": "C", "score": "6-2 6-2", "status": "completed"},
        ])
        fitted = fit_power_ratings_from_df(rows)
        self.assertEqual(len(fitted.ratings), 3)
        self.assertGreater(float(fitted.ratings.iloc[0].power), float(fitted.ratings.iloc[-1].power))
        self.assertEqual(MATCH_EVIDENCE_CAP_GAMES, 28.0)


class MatchProbabilityTests(unittest.TestCase):
    def test_even_game_probability_means_even_match_probability(self):
        self.assertAlmostEqual(set_win_probability(0.5), 0.5, places=9)
        self.assertAlmostEqual(match_win_probability(0.5, 3), 0.5, places=9)
        self.assertAlmostEqual(match_win_probability(0.5, 5), 0.5, places=9)

    def test_best_of_five_rewards_the_stronger_player(self):
        self.assertGreater(match_win_probability(0.60, 5), match_win_probability(0.60, 3))


if __name__ == "__main__":
    unittest.main()
