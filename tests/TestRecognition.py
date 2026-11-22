import unittest
from unittest.mock import Mock

from PIL import Image

from wuwa_score.ocr import EchoReader
from wuwa_score.recognition import TextBox, clean, find_echo, find_equipped_template


def box(text, x, y, right):
    return TextBox(clean(text), x, y, right, 0.026)


def detail_boxes():
    # The reported 1600×900 frame had sparkles recognized as plus signs.
    boxes = [box("COST4", .39, .176, .51), box("声骸技能", .38, .454, .51)]
    for name, value, y in (
        ("治疗效果加成", "26.4%", .214),
        ("攻击", "150", .250),
        ("+共鸣效率", "10.0%", .286),
        ("＋暴击", "6.3%", .317),
        ("✦重击伤害加成", "9.4%", .351),
        ("+攻击", "7.9%", .381),
        ("+共鸣技能伤害加成", "7.1%", .414),
    ):
        boxes.extend((box(name, .39, y, .69), box(value, .79, y + .003, .89)))
    return boxes


class TestEchoRecognition(unittest.TestCase):
    def test_reads_all_five_substats_with_ocr_sparkles(self):
        echo = find_echo(detail_boxes(), tuning=False)
        self.assertEqual(4, echo.cost)
        self.assertEqual(26.4, echo.main_rows[0].value)
        self.assertEqual(
            [("共鸣效率", 10.0), ("暴击", 6.3), ("重击", 9.4),
             ("攻击%", 7.9), ("共鸣技能", 7.1)],
            [(row.stat_name, row.value) for row in echo.sub_rows],
        )

    def test_inline_sparkle_and_stat_value(self):
        boxes = detail_boxes()[:-2]
        boxes.append(box("+共鸣技能伤害加成7.1%", .39, .414, .89))
        echo = find_echo(boxes, tuning=False)
        self.assertEqual(5, len(echo.sub_rows))
        self.assertEqual("共鸣技能", echo.sub_rows[-1].stat_name)

    def test_cost_three_with_countermeasure_skill_heading(self):
        for heading in ("声骸技能 对策技", "聲骸技能：對策技"):
            with self.subTest(heading=heading):
                boxes = [box("COST 3", .39, .176, .51), box(heading, .38, .454, .62)]
                for name, value, y in (
                    ("@共鸣效率", "32.0%", .217),
                    ("X攻击", "100", .250),
                    ("+重击伤害加成", "11.6%", .283),
                    ("+攻击", "7.9%", .317),
                    ("+生命", "510", .349),
                    ("+共鸣效率", "9.2%", .381),
                    ("+生命", "7.9%", .412),
                ):
                    boxes.extend((box(name, .39, y, .63), box(value, .79, y, .89)))
                echo = find_echo(boxes, tuning=False)
                self.assertEqual(3, echo.cost)
                self.assertEqual([11.6, 7.9, 510, 9.2, 7.9], [row.value for row in echo.sub_rows])
                self.assertIsNone(find_echo(boxes[:1] + boxes[2:], tuning=False))

    def test_crop_retry_recovers_a_missing_final_row(self):
        reader = EchoReader.__new__(EchoReader)
        boxes = detail_boxes()
        reader._read_boxes = Mock(side_effect=[boxes[:-2], boxes])
        echo = reader._read_panel(Image.new("RGB", (560, 747)), 1600, 900,
                                 origin_x=1040, tuning=False)
        self.assertEqual(5, len(echo.sub_rows))
        self.assertEqual(7, len(echo.anchors))
        self.assertAlmostEqual((1040 + .39 * 560) / 1600, echo.anchors[-1].left)
        self.assertAlmostEqual(.414 + .013, echo.anchors[-1].center_y)
        self.assertEqual(("stats", False), reader._read_boxes.call_args.args[0])
        self.assertEqual(1.5, reader._read_boxes.call_args.kwargs["scale"])

    def test_unrolled_echo_keeps_zero_substats(self):
        boxes = detail_boxes()[:6]
        self.assertEqual((), find_echo(boxes, tuning=False).sub_rows)

    def test_matches_badge_and_reference_variant_order(self):
        for badge, expected in (
            ("维里奈装配中", "维里奈-通用"),
            ("洛瑟菈装配中", "洛瑟菈-声骸-羽落"),
            ("莉莉装配中", "莉莉-通用"),
            ("鎖暝裝配中", "锁暝-通用"),
            ("心装配中", "心-通用"),
            ("鉴心装配中", "鉴心-通用"),
            ("陌生心装配中", None),
        ):
            with self.subTest(badge=badge):
                self.assertEqual(expected, find_equipped_template([box(badge, .42, .87, .63)]))

    def test_matches_split_badge_only_on_same_line(self):
        marker = box("装配中", .52, .87, .61)
        self.assertEqual(
            "维里奈-通用",
            find_equipped_template([marker, box("维里奈", .42, .871, .51)]),
        )
        self.assertIsNone(find_equipped_template([marker, box("维里奈", .42, .80, .51)]))
        self.assertIsNone(find_equipped_template([box("维里奈", .42, .871, .51)]))
        self.assertEqual(
            "鉴心-通用",
            find_equipped_template([box("心装配中", .52, .87, .63), box("鉴", .47, .87, .51)]),
        )
