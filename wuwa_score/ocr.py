"""Standalone PP-OCRv5 adapter using the same models as okww."""

from dataclasses import replace

import cv2
import numpy as np
from PIL import Image
from onnxocr.onnx_paddleocr import ONNXPaddleOcr

from .recognition import TextBox, clean, find_echo, find_equipped_template, stat_region


class EchoReader:
    def __init__(self):
        self.model = ONNXPaddleOcr(
            use_openvino=True, use_npu=False, use_angle_cls=False, det_limit_side_len=1280
        )
        self.previous = {}
        self.equipped_template = None

    def read(self, image):
        image = image.convert("RGB")
        width, height = image.size
        if height > 1080:
            image = image.resize((round(width * 1080 / height), 1080), Image.Resampling.LANCZOS)
            width, height = image.size

        # The left and right panels anchor to their respective window edges
        # on wider displays. Size their search areas from the 16:9 layout.
        layout_width = min(width, height * 16 / 9)
        left = image.crop((0, 0, round(layout_width * 0.41), round(height * 0.57)))
        echo = self._read_panel(left, height, tuning=True)
        if echo is not None:
            return replace(echo, equipped_template=self.equipped_template)

        right_edge = width - round(layout_width * 0.35)
        right = image.crop((right_edge, 0, width, round(height * 0.83)))
        echo = self._read_panel(right, height, tuning=False)
        if echo is None:
            self.equipped_template = None
            return None

        badge_top = round(height * 0.76)
        badge = image.crop((right_edge, badge_top, width, round(height * 0.96)))
        boxes = self._read_boxes("equipped", badge, height, top=badge_top, scale=1.5)
        self.equipped_template = find_equipped_template(boxes)
        return replace(echo, equipped_template=self.equipped_template)

    def _read_panel(self, panel, height, *, tuning):
        boxes = self._read_boxes(("panel", tuning), panel, height)
        region = stat_region(boxes, tuning=tuning)
        if region is None or region[1] <= region[0]:
            return None
        echo = find_echo(boxes, tuning=tuning, region=region)
        if echo is not None and len(echo.sub_rows) == 5:
            return echo

        # Give small or low-contrast rows a second pass without the rest of
        # the screen competing for detector resolution.
        top, bottom = region
        start = round(height * (top - 0.01))
        end = min(panel.height, round(height * (bottom + 0.01)))
        stats = panel.crop((0, start, panel.width, end))
        detailed = self._read_boxes(("stats", tuning), stats, height, top=start, scale=1.5)
        context = [box for box in boxes if not top <= box.center_y < bottom]
        reread = find_echo(context + detailed, tuning=tuning, region=region)
        if reread is not None and (echo is None or len(reread.sub_rows) > len(echo.sub_rows)):
            return reread
        return echo

    def _read_boxes(self, key, panel, height, *, top=0, scale=1.0):
        signature = (panel.size, height, top, panel.tobytes())
        previous = self.previous.get(key)
        if previous is not None and previous[0] == signature:
            return previous[1]

        sample = panel
        if scale != 1.0:
            size = (round(panel.width * scale), round(panel.height * scale))
            sample = panel.resize(size, Image.Resampling.BICUBIC)
        bgr = cv2.cvtColor(np.asarray(sample), cv2.COLOR_RGB2BGR)
        polygons, texts = self.model(bgr, cls=False)
        boxes = []
        if polygons is not None:
            y_scale = panel.height / sample.height / height
            for points, (text, confidence) in zip(polygons, texts):
                if confidence < 0.60:
                    continue
                xs, ys = zip(*points)
                boxes.append(TextBox(
                    clean(text), min(xs) / sample.width, top / height + min(ys) * y_scale,
                    max(xs) / sample.width, (max(ys) - min(ys)) * y_scale,
                ))
        self.previous[key] = signature, boxes
        return boxes
