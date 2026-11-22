"""Read the stat rows of a single Chinese Echo panel."""

from dataclasses import dataclass
import re
import unicodedata

from .scoring import EQUIPPED_TEMPLATES, MAX_MAINSTAT_VALUES, MAX_SUBSTAT_VALUES


RIGHT_HEADINGS = ("声骸技能", "合鸣效果")
LEFT_HEADINGS = ("声骸强化", "强化并调谐", "已完成全部调谐")
STAT_ALIASES = {
    "暴击率": "暴击",
    "治疗效果": "治疗效果加成",
    "普攻伤害加成": "普攻",
    "普通攻击伤害加成": "普攻",
    "重击伤害加成": "重击",
    "共鸣技能伤害加成": "共鸣技能",
    "共鸣解放伤害加成": "共鸣解放",
}
STAT_NAMES = set(MAX_SUBSTAT_VALUES).union(
    *(primary for primary, _ in MAX_MAINSTAT_VALUES.values())
)
STAT_LABEL_PREFIX = "+✦✧✶✷·•・●▪"
NUMBER = r"(?:\+?\d+(?:[.,]\d+)*%?|[.·。]\d{2,4})"
INLINE_STAT = re.compile(rf"(.+?)({NUMBER})$")
COST = re.compile(r"(?:COST|C0ST)[:：]?([134])?", re.IGNORECASE)
TRADITIONAL_TEXT = str.maketrans({
    "聲": "声", "強": "强", "並": "并", "調": "调", "諧": "谐", "鳴": "鸣",
    "裝": "装", "擊": "击", "撃": "击", "傷": "伤", "療": "疗", "禦": "御",
    "導": "导", "電": "电", "氣": "气", "熱": "热", "滅": "灭", "寧": "宁", "達": "达",
    "貝": "贝", "霽": "霁", "聖": "圣", "蘿": "萝", "爾": "尔", "維": "维",
    "愛": "爱", "彌": "弥", "鎖": "锁", "鑑": "鉴",
})


@dataclass(frozen=True)
class TextBox:
    text: str
    x: float
    y: float
    right: float
    height: float

    @property
    def center_y(self):
        return self.y + self.height / 2


@dataclass(frozen=True)
class StatRow:
    stat_name: str
    value: float
    value_text: str


@dataclass(frozen=True)
class Echo:
    cost: int
    main_rows: tuple[StatRow, ...]
    sub_rows: tuple[StatRow, ...]
    equipped_template: str | None = None


def clean(text):
    normalized = unicodedata.normalize("NFKC", text).translate(TRADITIONAL_TEXT)
    return "".join(normalized.split())


def _stat_name(label, percent):
    # OCR sees the sparkle at the start of the row as "+" on real frames.
    label = label.lstrip(STAT_LABEL_PREFIX)
    label = STAT_ALIASES.get(label, label)
    if label in ("攻击", "防御", "生命") and percent:
        label += "%"
    return label if label in STAT_NAMES else None


def _stat_row(label, number):
    name = _stat_name(label, number.endswith("%"))
    if name is None:
        return None
    if number.endswith("%") != (name not in ("攻击", "防御", "生命")):
        return None
    value = number.lstrip("+.·。").rstrip("%")
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+", value):
        value = value.replace(",", "")
    else:
        value = value.replace(",", ".")
    try:
        numeric = float(value)
    except ValueError:
        return None
    if not 0 < numeric <= 2280:
        return None
    return StatRow(name, numeric, number)


def _same_line(first, second):
    return abs(first.center_y - second.center_y) <= max(
        0.010, min(first.height, second.height) * 0.60
    )


def find_equipped_template(boxes):
    """Match the equipped badge, including when OCR splits its name and suffix."""
    for box in boxes:
        if not box.text.endswith("装配中"):
            continue
        character = box.text.removesuffix("装配中").lstrip(STAT_LABEL_PREFIX)
        preceding = [
            other for other in boxes
            if other.x < box.x and -0.025 <= box.x - other.right <= 0.12
            and _same_line(other, box)
        ]
        for other in sorted(preceding, key=lambda item: item.right, reverse=True):
            if template := EQUIPPED_TEMPLATES.get(other.text.lstrip(STAT_LABEL_PREFIX) + character):
                return template
        if template := EQUIPPED_TEMPLATES.get(character):
            return template
    return None


def _rows(boxes):
    values = [box for box in boxes if re.fullmatch(NUMBER, box.text)]
    rows = []
    for box in sorted(boxes, key=lambda item: item.center_y):
        combined = INLINE_STAT.fullmatch(box.text)
        if combined and (row := _stat_row(*combined.groups())):
            rows.append((box, row))
            continue
        if not _stat_name(box.text, False) and not _stat_name(box.text, True):
            continue
        matches = [
            value for value in values
            if value.x >= box.right - 0.03 and _same_line(box, value)
        ]
        if matches:
            value = max(matches, key=lambda item: item.right)
            values.remove(value)
            row = _stat_row(box.text, value.text)
        else:
            row = None
        rows.append((box, row))
    return rows


def _infer_cost(boxes, primary, fixed):
    compatible = {
        cost: (main_values[primary.stat_name], fixed_values[fixed.stat_name])
        for cost, (main_values, fixed_values) in MAX_MAINSTAT_VALUES.items()
        if primary.stat_name in main_values and fixed.stat_name in fixed_values
    }
    for box in boxes:
        match = COST.fullmatch(box.text)
        if not match:
            continue
        value = match[1]
        if value is None:
            digits = [
                other for other in boxes
                if other.text in ("1", "3", "4")
                and -0.03 <= other.x - box.right <= 0.28
                and _same_line(box, other)
            ]
            if digits:
                value = min(digits, key=lambda other: abs(other.x - box.right)).text
        if value is not None and int(value) in compatible:
            return int(value)

    # Both main stats scale with enhancement level. Comparing their
    # proportions distinguishes 3 COST from 4 COST on an unlevelled Echo.
    candidates = []
    for cost, (main_max, fixed_max) in compatible.items():
        fixed_ratio = fixed.value / fixed_max
        if 0.19 <= fixed_ratio <= 1.01 and abs(primary.value / main_max - fixed_ratio) <= 0.025:
            candidates.append(cost)
    if len(candidates) == 1:
        return candidates[0]
    return None


def stat_region(boxes, *, tuning):
    headings = LEFT_HEADINGS if tuning else RIGHT_HEADINGS
    markers = [box for box in boxes if box.text.rstrip(":") in headings]
    if not markers:
        return None
    return 0.17, 0.57 if tuning else min(box.y for box in markers)


def find_echo(boxes, *, tuning, region=None):
    region = region or stat_region(boxes, tuning=tuning)
    if region is None:
        return None
    top, bottom = region
    pairs = _rows([box for box in boxes if top <= box.center_y < bottom])
    if not 2 <= len(pairs) <= 7 or any(row is None for _, row in pairs):
        return None
    primary, fixed, *sub_rows = [row for _, row in pairs]
    if any(row.stat_name not in MAX_SUBSTAT_VALUES for row in sub_rows):
        return None
    if len({row.stat_name for row in sub_rows}) != len(sub_rows):
        return None
    if any(row.value > MAX_SUBSTAT_VALUES[row.stat_name] for row in sub_rows):
        return None
    if len(pairs) > 2:
        # A missed line between two stat rows would inflate the potential score.
        centers = [box.center_y for box, _ in pairs]
        if any(second - first > 0.065 for first, second in zip(centers, centers[1:])):
            return None
    cost_boxes = [box for box in boxes if box.center_y < pairs[0][0].center_y]
    cost = _infer_cost(cost_boxes, primary, fixed)
    if cost is None:
        return None
    return Echo(cost, (primary, fixed), tuple(sub_rows))
