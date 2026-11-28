"""Run the PP-OCRv6 predictors with Windows hardware acceleration."""

import logging

import numpy as np

from onnxocr.onnx_paddleocr import ONNXPaddleOcr
from onnxocr.predict_base import PredictBase
from onnxocr.predict_det import TextDetector
from onnxocr.predict_rec import TextRecognizer


PROVIDER = "DmlExecutionProvider"


class _DirectMLPredictor(PredictBase):
    # Keep ONNXPaddleOcr's preprocessing, postprocessing and ONNX input
    # helpers, and supply a GPU session in place of its CPU-only loader.
    def __init__(self, model_path, *args):
        import onnxruntime as ort

        devices = [
            device for device in ort.get_ep_devices()
            if device.ep_name == PROVIDER
            and device.device.type == ort.OrtHardwareDeviceType.GPU
            and device.device.vendor_id != 0x1414  # Microsoft software adapter
        ]
        if not devices:
            raise RuntimeError("No DirectML hardware GPU is available")
        device = min(
            devices, key=lambda item: int(item.device.metadata.get("DxgiHighPerformanceIndex", "999")),
        )

        options = ort.SessionOptions()
        options.enable_mem_pattern = False
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.log_severity_level = 3
        options.add_provider_for_devices([device], {})
        self.is_openvino = False
        self.session = ort.InferenceSession(model_path, sess_options=options)
        self.session.disable_fallback()
        if PROVIDER not in self.session.get_providers():
            raise RuntimeError("ONNX Runtime did not enable DirectML")
        name = self.session.get_inputs()[0].name
        self.session.run(None, {name: np.zeros(self.probe_shape, dtype=np.float32)})
        logging.getLogger(__name__).info(
            "DirectML OCR device: %s", device.device.metadata.get("Description", "GPU"),
        )


class _DirectMLDetector(TextDetector, _DirectMLPredictor):
    probe_shape = (1, 3, 128, 128)


class _DirectMLRecognizer(TextRecognizer, _DirectMLPredictor):
    probe_shape = (1, 3, 48, 320)


class DirectMLOcr(ONNXPaddleOcr):
    def _initialize_models(self, params):
        self.text_detector = _DirectMLDetector(params)
        self.text_recognizer = _DirectMLRecognizer(params)
        self.use_angle_cls = False
        self.drop_score = params.drop_score
        self.args = params
        self.crop_image_res_index = 0
