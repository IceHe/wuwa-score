"""Standalone adapter for the PP-OCRv6 small models used by installed OKWW."""

from dataclasses import replace
import logging

import cv2
import numpy as np
from PIL import Image
from onnxocr.onnx_paddleocr import ONNXPaddleOcr

from .recognition import TextBox, clean, find_echo, find_equipped_names, stat_region


OCR_OPTIONS = {"use_npu": False, "use_angle_cls": False, "det_limit_side_len": 1280}


def load_gpu_model():
    try:
        from .directml import DirectMLOcr
        return DirectMLOcr(use_openvino=False, **OCR_OPTIONS)
    except Exception as error:
        logging.getLogger(__name__).info("DirectML OCR unavailable: %s", error)
        return None


def echo_panel_signature(image, echo):
    """Sample high-contrast text near the recognized labels and values."""
    width, height = image.size
    layout_width = min(width, height * 16 / 9)
    label_left = min(anchor.left for anchor in echo.anchors) * width
    tuning = label_left < width / 2
    value_right = layout_width * 0.37 if tuning else width - layout_width * 0.025
    label_right = label_left + layout_width * 0.13
    top = max(0.07, echo.anchors[0].center_y - 0.14) * height
    bottom = min(0.83, echo.anchors[-1].center_y + 0.065) * height
    regions = [
        (label_left, top, label_right, bottom),
        (value_right - layout_width * 0.11, (echo.anchors[0].center_y - 0.02) * height,
         value_right, bottom),
    ]
    if not tuning:
        regions.append((label_left, height * 0.85, label_right, height * 0.90))

    signatures = []
    scale = 900 / height
    for left, top, right, bottom in regions:
        crop = image.crop((round(left), round(top), min(width, round(right)), round(bottom)))
        size = (max(1, round(crop.width * scale)), max(1, round(crop.height * scale)))
        pixels = np.asarray(crop.convert("L").resize(size, Image.Resampling.BILINEAR))
        # Use bright strokes with local contrast, so changes to the blurred
        # background and dark score overlays to the left do not trigger OCR.
        contrast = pixels - cv2.erode(pixels, None)
        signatures.append((pixels, (pixels >= 155) & (contrast >= 30)))
    return signatures


def echo_panel_changed(before, after):
    # Check bands separately so a changed digit can outweigh a still panel.
    band = np.ones(10, dtype=np.int32)
    for (old, old_text), (new, new_text) in zip(before, after):
        changed = (old_text | new_text) & (cv2.absdiff(old, new) >= 35)
        counts = np.count_nonzero(changed, axis=1)
        if np.convolve(counts, band, mode="valid").max() >= 22:
            return True
    return False


class EchoReader:
    def __init__(self):
        self.model = ONNXPaddleOcr(use_openvino=True, **OCR_OPTIONS)
        self.previous = {}
        self.equipped_names = ()

    def use_model(self, model):
        self.model = model
        self.previous.clear()

    def read(self, image, *, prefer_tuning=True):
        image = image.convert("RGB")
        width, height = image.size
        if height > 1080:
            image = image.resize((round(width * 1080 / height), 1080), Image.Resampling.LANCZOS)
            width, height = image.size

        # The left and right panels anchor to their respective window edges
        # on wider displays. Size their search areas from the 16:9 layout.
        layout_width = min(width, height * 16 / 9)
        right_edge = width - round(layout_width * 0.35)
        for tuning in (prefer_tuning, not prefer_tuning):
            if tuning:
                origin = 0
                panel = image.crop((0, 0, round(layout_width * 0.41), round(height * 0.57)))
            else:
                origin = right_edge
                panel = image.crop((right_edge, 0, width, round(height * 0.83)))
            echo = self._read_panel(panel, width, height, origin_x=origin, tuning=tuning)
            if echo is None:
                continue
            if not tuning:
                badge_top = round(height * 0.76)
                badge = image.crop((right_edge, badge_top, width, round(height * 0.96)))
                boxes = self._read_boxes("equipped", badge, height, top=badge_top, scale=1.5)
                self.equipped_names = find_equipped_names(boxes)
            return replace(echo, equipped_names=self.equipped_names)
        self.equipped_names = ()
        return None

    def _read_panel(self, panel, width, height, *, origin_x, tuning):
        boxes = self._read_boxes(("panel", tuning), panel, height)
        region = stat_region(boxes, tuning=tuning)
        if region is None or region[1] <= region[0]:
            return None
        echo = find_echo(boxes, tuning=tuning, region=region)
        if echo is None or len(echo.sub_rows) < 5:
            # Re-read the rows at a larger scale when a separate box was lost.
            top, bottom = region
            start = round(height * (top - 0.01))
            end = min(panel.height, round(height * (bottom + 0.01)))
            stats = panel.crop((0, start, panel.width, end))
            detailed = self._read_boxes(("stats", tuning), stats, height, top=start, scale=1.5)
            context = [box for box in boxes if not top <= box.center_y < bottom]
            reread = find_echo(context + detailed, tuning=tuning, region=region)
            if reread is not None and (echo is None or len(reread.sub_rows) > len(echo.sub_rows)):
                echo = reread
        if echo is None:
            return None

        # OCR uses the crop's x coordinates. The overlay uses the full client.
        anchors = tuple(
            replace(anchor, left=(origin_x + anchor.left * panel.width) / width)
            for anchor in echo.anchors
        )
        return replace(echo, anchors=anchors)

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
