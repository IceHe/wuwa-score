"""Standalone PP-OCRv5 adapter using the same models as okww."""

import cv2
import numpy as np
from PIL import Image
from onnxocr.onnx_paddleocr import ONNXPaddleOcr

from .recognition import TextBox, clean, find_echo


class EchoReader:
    def __init__(self):
        self.model = ONNXPaddleOcr(
            use_openvino=True, use_npu=False, use_angle_cls=False, det_limit_side_len=960
        )
        self.previous = {}

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
            return echo
        right = image.crop((width - round(layout_width * 0.35), 0, width, round(height * 0.79)))
        return self._read_panel(right, height, tuning=False)

    def _read_panel(self, panel, height, *, tuning):
        signature = (panel.size, height, panel.tobytes())
        previous = self.previous.get(tuning)
        if previous is not None and previous[0] == signature:
            return previous[1]

        width = panel.width
        bgr = cv2.cvtColor(np.asarray(panel), cv2.COLOR_RGB2BGR)
        polygons, texts = self.model(bgr, cls=False)
        boxes = []
        if polygons is not None:
            for points, (text, confidence) in zip(polygons, texts):
                if confidence < 0.60:
                    continue
                xs, ys = zip(*points)
                boxes.append(TextBox(
                    clean(text), min(xs) / width, min(ys) / height,
                    max(xs) / width, (max(ys) - min(ys)) / height,
                ))
        echo = find_echo(boxes, tuning=tuning)
        self.previous[tuning] = signature, echo
        return echo
