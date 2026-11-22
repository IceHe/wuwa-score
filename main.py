"""Run wuwa-score directly from its source directory."""

import argparse
from pathlib import Path
import sys

from wuwa_score.scoring import DEFAULT_TEMPLATE, calculate_echo_score, substat_tier_label, template_names


def score_image(path, template):
    from PIL import Image
    from wuwa_score.ocr import EchoReader

    with Image.open(path) as image:
        echo = EchoReader().read(image)
    if echo is None:
        print("未识别到完整的单个声骸面板。", file=sys.stderr)
        return 1
    score = calculate_echo_score(template, echo.cost, echo.main_rows, echo.sub_rows)
    print(f"{template} · {echo.cost} COST")
    print(f"当前评分 {score.current_score:.2f} · 理论最高 {score.potential_score:.2f}")
    for index, (row, points) in enumerate(zip(echo.main_rows + echo.sub_rows, score.row_scores)):
        tier = "主词条" if index < len(echo.main_rows) else substat_tier_label(row.stat_name, row.value)
        print(f"{row.stat_name}  {row.value_text}  {tier}  +{points:.2f}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="鸣潮声骸实时评分")
    parser.add_argument("--image", type=Path, metavar="PATH", help="评估本地游戏截图并输出到终端")
    parser.add_argument("--template", default=DEFAULT_TEMPLATE, metavar="NAME", help="初始评分模板")
    args = parser.parse_args()
    if args.template not in template_names():
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
