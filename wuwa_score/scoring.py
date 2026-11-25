"""XW-UID-compatible score calculation for one Echo.

Adapted for wuwa-score from ok-wuthering-waves (feat-echo-score, 5b8253b1)
on 2026-11-22. See LICENSE.txt.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from itertools import combinations
import json
import math
from pathlib import Path

TEMPLATE_FILE = Path(__file__).with_name("templates.json")
SCORE_PER_ECHO = 50.0
ELEMENT_NAMES = {"冷凝", "热熔", "导电", "气动", "衍射", "湮灭"}
SKILL_WEIGHT_INDEX = {
    "普攻伤害加成": 0,
    "重击伤害加成": 1,
    "共鸣技能伤害加成": 2,
    "共鸣解放伤害加成": 3,
}
_SHORT_SKILL_NAMES = {
    "普攻": "普攻伤害加成",
    "重击": "重击伤害加成",
    "共鸣技能": "共鸣技能伤害加成",
    "共鸣解放": "共鸣解放伤害加成",
}
SUBSTAT_TIERS = {
    "暴击": (6.3, 6.9, 7.5, 8.1, 8.7, 9.3, 9.9, 10.5),
    "暴击伤害": (12.6, 13.8, 15.0, 16.2, 17.4, 18.6, 19.8, 21.0),
    "攻击%": (6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6),
    "防御%": (8.1, 9.0, 10.0, 10.9, 11.8, 12.8, 13.8, 14.7),
    "生命%": (6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6),
    "攻击": (30.0, 40.0, 50.0, 60.0),
    "防御": (40.0, 50.0, 60.0, 70.0),
    "生命": (320.0, 360.0, 390.0, 430.0, 470.0, 510.0, 540.0, 580.0),
    "共鸣效率": (6.8, 7.6, 8.4, 9.2, 10.0, 10.8, 11.6, 12.4),
    "普攻": (6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6),
    "重击": (6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6),
    "共鸣技能": (6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6),
    "共鸣解放": (6.4, 7.1, 7.9, 8.6, 9.4, 10.1, 10.9, 11.6),
}
MAX_SUBSTAT_VALUES = {name: tiers[-1] for name, tiers in SUBSTAT_TIERS.items()}

# Relative weights reproduce Kuro's published percentages rounded to four
# decimal places. The weights follow SUBSTAT_TIERS from lowest to highest.
_STANDARD_TIER_WEIGHTS = (7, 8, 21, 25, 18, 15, 6, 3)
_CRIT_TIER_WEIGHTS = (70, 70, 70, 24, 24, 24, 9, 9)
_SUBSTAT_TIER_WEIGHTS = {
    "暴击": _CRIT_TIER_WEIGHTS,
    "暴击伤害": _CRIT_TIER_WEIGHTS,
    "攻击%": _STANDARD_TIER_WEIGHTS,
    "防御%": _STANDARD_TIER_WEIGHTS,
    "生命%": _STANDARD_TIER_WEIGHTS,
    "攻击": (7, 54, 39, 3),
    "防御": (15, 46, 33, 9),
    "生命": _STANDARD_TIER_WEIGHTS,
    "共鸣效率": _STANDARD_TIER_WEIGHTS,
    "普攻": _STANDARD_TIER_WEIGHTS,
    "重击": _STANDARD_TIER_WEIGHTS,
    "共鸣技能": _STANDARD_TIER_WEIGHTS,
    "共鸣解放": _STANDARD_TIER_WEIGHTS,
}
MAX_MAINSTAT_VALUES = {
    1: (
        {"攻击%": 18.0, "生命%": 22.8, "防御%": 22.8},
        {"生命": 2280.0},
    ),
    3: (
        {
            "攻击%": 30.0,
            "生命%": 30.0,
            "防御%": 38.0,
            "共鸣效率": 32.0,
            "冷凝伤害加成": 30.0,
            "热熔伤害加成": 30.0,
            "导电伤害加成": 30.0,
            "气动伤害加成": 30.0,
            "衍射伤害加成": 30.0,
            "湮灭伤害加成": 30.0,
        },
        {"攻击": 100.0},
    ),
    4: (
        {
            "攻击%": 33.0,
            "生命%": 33.0,
            "防御%": 41.5,
            "暴击": 22.0,
            "暴击伤害": 44.0,
            "治疗效果加成": 26.0,
        },
        {"攻击": 150.0},
    ),
}


@dataclass(frozen=True)
class EchoScoreResult:
    cost: int
    row_scores: tuple[float, ...]
    current_score: float
    potential_score: float
    double_crit_probability: float
    potential_score_probability: float


def _build_template_options(templates):
    rows = [
        (str(char_id), variant, template)
        for char_id, variants in templates.items()
        for variant, template in variants.items()
    ]
    duplicate_names = Counter(template["name"] for _, _, template in rows)
    options = {}
    for char_id, variant, template in rows:
        label = template["name"]
        if duplicate_names[label] > 1:
            label = f"{label}（{char_id}）"
        options[label] = (char_id, variant, template)
    return options


@dataclass(frozen=True)
class TemplateCatalog:
    options: dict[str, tuple[str, str, dict]]
    equipped: dict[str, str]
    default: str

    def resolve(self, name):
        if name in self.options:
            return name
        if name == "通用":
            return self.default
        return next((label for label in self.options if label.startswith(f"{name}-")), self.default)


def _load_catalog(path):
    with path.open(encoding="utf-8") as snapshot:
        templates = json.load(snapshot)["templates"]
    options = _build_template_options(templates)
    default = templates["default"]["default"]["name"]
    # Match the OKWW plugin's choice of the last variant for each character.
    equipped = {
        label.partition("-")[0]: label
        for label in options
        if label != default and "-" in label
    }
    return TemplateCatalog(options, equipped, default)


_catalog = _load_catalog(TEMPLATE_FILE)


def reload_templates(path=TEMPLATE_FILE):
    """Load the whole replacement before making it visible to OCR and scoring."""
    global _catalog
    updated = _load_catalog(path)
    changed = updated != _catalog
    _catalog = updated
    return changed


def default_template():
    return _catalog.default


def format_template_label(name, *, automatic=False, user_specified=False):
    if automatic:
        return f"{name}（自动匹配）"
    if user_specified:
        return f"{name}（用户指定）"
    return name


def template_for_equipped_names(names):
    equipped = _catalog.equipped
    return next((equipped[name] for name in names if name in equipped), None)


def template_names():
    """Return character and variant templates as unique display labels."""
    return list(_catalog.options)


def substat_tier(stat_name, value):
    """Return ``(tier, total_tiers)`` for the closest in-game roll value."""
    tiers = SUBSTAT_TIERS.get(stat_name)
    if not tiers:
        return None
    tier_index = min(range(len(tiers)), key=lambda index: abs(tiers[index] - float(value)))
    return tier_index + 1, len(tiers)


def substat_tier_label(stat_name, value):
    """Return the closest in-game roll tier, such as ``1档`` or ``8档``."""
    tier = substat_tier(stat_name, value)
    return f"{tier[0]}档" if tier else ""


def resolve_template_name(template_name):
    """Resolve an exact option or migrate a legacy bare character name."""
    return _catalog.resolve(template_name)


def _selected_template(template_name):
    catalog = _catalog
    return catalog.options[catalog.resolve(template_name)][2]


def _main_name(name):
    if name.endswith("伤害加成") and name.removesuffix("伤害加成") in ELEMENT_NAMES:
        return "属性伤害加成"
    return name


def _entry_weight(index, name, cost, template):
    if index < 2:
        return float(template.get("main_props", {}).get(str(cost), {}).get(_main_name(name), 0.0))

    name = _SHORT_SKILL_NAMES.get(name, name)
    sub_weights = template.get("sub_props", {})
    if name in SKILL_WEIGHT_INDEX:
        generic_weight = float(sub_weights.get("技能伤害加成", 0.0))
        skill_weights = template.get("skill_weight", [0.0, 0.0, 0.0, 0.0])
        return generic_weight * float(skill_weights[SKILL_WEIGHT_INDEX[name]])
    return float(sub_weights.get(name, 0.0))


def _truncate_2(value):
    return math.trunc((value + 1e-12) * 100.0) / 100.0


def _max_main_value(cost, index, row):
    """Return the +25 value for this main-stat slot, or its observed value."""
    slots = MAX_MAINSTAT_VALUES.get(int(cost), ())
    if index >= len(slots):
        return row.value
    return slots[index].get(row.stat_name, row.value)


def _double_crit_probability(existing_substats, remaining_slots):
    missing = len({"暴击", "暴击伤害"} - existing_substats)
    if missing == 0:
        return 1.0
    if missing > remaining_slots:
        return 0.0

    # All still-available types are equally likely and cannot repeat.
    available = len(MAX_SUBSTAT_VALUES) - len(existing_substats)
    qualifying = math.comb(available - missing, remaining_slots - missing)
    return qualifying / math.comb(available, remaining_slots)


def _potential_score_probability(candidates, remaining_slots, score_substat):
    if remaining_slots == 0:
        return 1.0

    cutoff = candidates[remaining_slots - 1][0]
    required, tied = [], []
    for maximum, name in candidates:
        if maximum < cutoff:
            break
        weights = _SUBSTAT_TIER_WEIGHTS[name]
        qualifying = sum(
            weight for tier, weight in zip(SUBSTAT_TIERS[name], weights, strict=True)
            if score_substat(name, tier) == maximum
        )
        probabilities = required if maximum > cutoff else tied
        probabilities.append(qualifying / sum(weights))

    # Every type above the cutoff must appear. Types at the cutoff may
    # substitute for one another, and each unordered set is equally likely.
    tied_slots = remaining_slots - len(required)
    tied_probability = math.fsum(math.prod(group) for group in combinations(tied, tied_slots))
    return math.prod(required) * tied_probability / math.comb(len(candidates), remaining_slots)


def format_probability(probability):
    """Keep a nonzero chance visible even when it is far below 0.01%."""
    if 0 < probability < 0.0001:
        return f"{probability * 100:.2e}%"
    return f"{probability:.2%}"


def calculate_echo_score(template_name, cost, main_rows, sub_rows):
    """Score OCR rows using XW-UID's per-entry truncation and 50-point scale."""
    template = _selected_template(template_name)
    try:
        maximum = float(template["score_max"][(1, 3, 4).index(int(cost))])
    except (KeyError, ValueError, IndexError, TypeError):
        return None
    if maximum <= 0:
        return None

    def score_substat(name, value):
        return _truncate_2(value * _entry_weight(2, name, cost, template) / maximum * SCORE_PER_ECHO)

    main_scores = tuple(
        _truncate_2(_max_main_value(cost, index, row)
                    * _entry_weight(index, row.stat_name, cost, template)
                    / maximum * SCORE_PER_ECHO)
        for index, row in enumerate(main_rows)
    )
    sub_scores = tuple(score_substat(row.stat_name, row.value) for row in sub_rows)
    row_scores = main_scores + sub_scores
    existing_substats = {row.stat_name for row in sub_rows}
    remaining_slots = max(0, 5 - len(sub_rows))
    candidates = sorted(
        ((score_substat(name, value), name) for name, value in MAX_SUBSTAT_VALUES.items()
         if name not in existing_substats),
        reverse=True,
    )
    potential_score = round(
        sum(row_scores) + sum(points for points, _ in candidates[:remaining_slots]),
        2,
    )
    return EchoScoreResult(
        cost=cost,
        row_scores=row_scores,
        current_score=round(sum(row_scores), 2),
        potential_score=potential_score,
        double_crit_probability=_double_crit_probability(existing_substats, remaining_slots),
        potential_score_probability=_potential_score_probability(candidates, remaining_slots, score_substat),
    )
