import math
import unittest
from unittest.mock import patch

from wuwa_score.recognition import StatRow
from wuwa_score.scoring import calculate_echo_score, format_probability


class TestPotentialScoreProbability(unittest.TestCase):
    def score(self, weights, *existing):
        template = {"score_max": [50, 50, 50], "sub_props": weights}
        rows = tuple(StatRow(name, 7.9, "7.9%") for name in existing)
        with patch("wuwa_score.scoring._selected_template", return_value=template):
            return calculate_echo_score("测试模板", 1, (), rows)

    def test_last_slot_uses_the_types_own_top_tier_odds(self):
        for name, top_tier in (("暴击", .03), ("攻击", 3 / 103), ("防御", 9 / 103)):
            with self.subTest(name=name):
                score = self.score({name: 1}, "攻击%", "共鸣效率", "生命%", "防御%")
                self.assertAlmostEqual(top_tier / 9, score.potential_score_probability)

    def test_counts_every_type_and_tier_that_ties_after_truncation(self):
        score = self.score(
            {"攻击": .0003, "防御": .00025}, "攻击%", "共鸣效率", "生命%", "防御%"
        )
        self.assertEqual(.01, score.potential_score)
        self.assertAlmostEqual((96 / 103 + 1) / 9, score.potential_score_probability)

    def test_required_types_and_interchangeable_final_type(self):
        score = self.score(
            {"暴击": 2, "暴击伤害": 1, "攻击%": 1, "生命%": 1}, "重击", "共鸣效率"
        )
        self.assertAlmostEqual(53.6, score.potential_score)
        expected = .03 ** 2 * (2 * 3 / 103) / math.comb(11, 3)
        self.assertAlmostEqual(expected, score.potential_score_probability)

    def test_finished_echo_and_zero_weight_template(self):
        complete = self.score({"暴击": 1}, "攻击%", "共鸣效率", "生命%", "防御%", "重击")
        self.assertEqual(complete.current_score, complete.potential_score)
        self.assertEqual(1, complete.potential_score_probability)
        self.assertEqual(1, self.score({}).potential_score_probability)

    def test_rare_nonzero_chance_has_a_nonzero_display(self):
        score = self.score({"暴击": 1, "暴击伤害": 1, "攻击%": 1, "生命%": 1, "防御%": 1})
        expected = .03 ** 2 * (3 / 103) ** 3 / math.comb(13, 5)
        self.assertAlmostEqual(expected, score.potential_score_probability, places=16)
        self.assertEqual("1.73e-09%", format_probability(score.potential_score_probability))
