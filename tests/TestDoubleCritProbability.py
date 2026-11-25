import unittest

from wuwa_score.recognition import StatRow
from wuwa_score.scoring import calculate_echo_score, default_template


class TestDoubleCritProbability(unittest.TestCase):
    def probability(self, *names, main_stat="攻击%"):
        main_rows = (StatRow(main_stat, 22, "22%"), StatRow("攻击", 150, "150"))
        sub_rows = tuple(StatRow(name, 7.9, "7.9%") for name in names)
        score = calculate_echo_score(default_template(), 4, main_rows, sub_rows)
        return score.double_crit_probability

    def test_fresh_echo_and_crit_main_stat_have_same_chance(self):
        for main_stat in ("攻击%", "暴击", "暴击伤害"):
            with self.subTest(main_stat=main_stat):
                self.assertAlmostEqual(5 / 39, self.probability(main_stat=main_stat))

    def test_two_missing_crit_stats(self):
        self.assertAlmostEqual(1 / 11, self.probability("共鸣效率"))
        self.assertAlmostEqual(1 / 45, self.probability("共鸣效率", "攻击%", "生命"))
        self.assertEqual(0, self.probability("共鸣效率", "攻击%", "生命", "防御"))

    def test_one_missing_crit_stat(self):
        for crit in ("暴击", "暴击伤害"):
            with self.subTest(crit=crit):
                self.assertAlmostEqual(1 / 3, self.probability(crit))
                self.assertAlmostEqual(1 / 9, self.probability(crit, "攻击%", "生命", "防御"))
                self.assertEqual(0, self.probability(crit, "攻击%", "生命", "防御", "重击"))

    def test_already_rolled_double_crit(self):
        self.assertEqual(1, self.probability("暴击", "暴击伤害"))
        self.assertEqual(1, self.probability("暴击", "暴击伤害", "攻击%", "生命", "防御"))
