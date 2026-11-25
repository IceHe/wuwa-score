"""Run wuwa-score directly from its source directory."""

import argparse
from pathlib import Path
import sys

from wuwa_score.scoring import (
    calculate_echo_score, default_template, format_probability, format_template_label,
    substat_tier_label, template_names,
)


def score_image(path, template):
    from PIL import Image
    from wuwa_score.ocr import EchoReader

    with Image.open(path) as image:
        echo = EchoReader().read(image)
    if echo is None:
        print("未识别到完整的单个声骸面板。", file=sys.stderr)
        return 1
    matched = echo.equipped_template if template is None else None
    name = template or matched or default_template()
    label = format_template_label(name, automatic=matched is not None, user_specified=template is not None)
    score = calculate_echo_score(name, echo.cost, echo.main_rows, echo.sub_rows)
    print(f"{label} · {echo.cost} COST")
    print(f"当前评分 {score.current_score:.2f} · 理论最高 {score.potential_score:.2f}")
    print(f"双暴概率 {score.double_crit_probability:.2%}")
    print(f"理论最高分概率 {format_probability(score.potential_score_probability)}")
    for index, (row, points) in enumerate(zip(echo.main_rows + echo.sub_rows, score.row_scores)):
        tier = "主词条" if index < len(echo.main_rows) else substat_tier_label(row.stat_name, row.value)
        print(f"{row.stat_name}  {row.value_text}  {tier}  +{points:.2f}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="鸣潮声骸实时评分")
    parser.add_argument("--image", type=Path, metavar="PATH", help="评估本地游戏截图并输出到终端")
    parser.add_argument("--template", metavar="NAME", help="实时评分的备用模板，或截图评分的指定模板")
    args = parser.parse_args()
    if args.template is not None and args.template not in template_names():
        parser.error(f"未知的评分模板：{args.template}")
    if args.image:
        try:
            return score_image(args.image, args.template)
        except OSError as error:
            parser.error(f"无法打开截图：{error}")
    if sys.platform != "win32":
        parser.error("实时评分需要 Windows")
    from wuwa_score.app import run

    run(args.template)
    return 0


if __name__ == "__main__":
    sys.exit(main())
