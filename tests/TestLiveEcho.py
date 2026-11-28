import queue
import threading
import unittest
from unittest.mock import Mock, patch

from PIL import Image, ImageDraw, ImageEnhance

from wuwa_score.app import ANALYZING_ECHO, GpuStatus, scan_live
from wuwa_score.capture import GameWindow
from wuwa_score.ocr import echo_panel_changed, echo_panel_signature
from wuwa_score.recognition import Echo, StatAnchor, StatRow


GAME = GameWindow(1, (0, 0, 1600, 900))


def sample(value):
    image = Image.new("RGB", (1600, 900), "#202838")
    outline = ImageDraw.Draw(image)
    x = 1490 + value
    outline.rectangle((x, 199, x + 5, 212), fill="#eee5d9")
    echo = Echo(
        3, (StatRow("攻击%", value, str(value)), StatRow("攻击", 100, "100")), (),
        anchors=(StatAnchor(0.8, 0.23), StatAnchor(0.8, 0.265)),
    )
    return image, echo


class TestLiveEcho(unittest.TestCase):
    def test_signature_follows_a_value_change_but_ignores_overlay_and_brightness(self):
        first, echo = sample(10)
        second, _ = sample(14)
        before = echo_panel_signature(first, echo)
        decorated = ImageEnhance.Brightness(first).enhance(0.94)
        ImageDraw.Draw(decorated).rectangle((1180, 196, 1274, 216), fill="#7ce5d4")
        self.assertFalse(echo_panel_changed(before, echo_panel_signature(decorated, echo)))
        self.assertTrue(echo_panel_changed(before, echo_panel_signature(second, echo)))

    def test_switch_clears_previous_score_and_discards_an_overtaken_result(self):
        first, second, third = (sample(value) for value in (10, 14, 19))
        frames = [first, first, first, first, second, third, third, third]
        updates = queue.SimpleQueue()
        stop = Mock(is_set=lambda: not frames)
        reader = Mock(equipped_names=())

        def read(image, *, prefer_tuning):
            echo = next(echo for pixels, echo in (first, second, third) if pixels is image)
            if image is second[0]:
                self.assertIn("OCR", updates.get_nowait().status)
                self.assertEqual(updates.get_nowait().echo, first[1])
                pending = updates.get_nowait()
                self.assertEqual(pending.status, ANALYZING_ECHO)
                self.assertTrue(pending.analyzing and pending.clear)
            return echo

        def capture():
            return frames.pop(0)[0], GAME

        reader.read.side_effect = read
        with patch("wuwa_score.ocr.EchoReader", return_value=reader):
            scan_live(updates, stop, capture=capture)

        self.assertEqual(reader.read.call_count, 3)
        self.assertEqual(updates.get_nowait().echo, third[1])
        self.assertTrue(updates.empty())

    def test_brief_transition_to_tuning_preserves_the_equipped_character(self):
        details, echo = sample(10)
        tuning = Image.new("RGB", details.size, "#202838")
        blank = tuning.copy()
        names = ("守岸人",)
        frames = [details, details, details, blank, tuning, tuning]
        updates = queue.SimpleQueue()
        stop = Mock(is_set=lambda: not frames)
        reader = Mock(equipped_names=())

        def read(image, *, prefer_tuning):
            if image is details:
                reader.equipped_names = names
                return echo
            if image is blank:
                reader.equipped_names = ()
                return None
            self.assertEqual(reader.equipped_names, names)
            return Echo(echo.cost, echo.main_rows, (), equipped_names=names,
                        anchors=(StatAnchor(0.12, 0.23), StatAnchor(0.12, 0.265)))

        reader.read.side_effect = read
        with patch("wuwa_score.ocr.EchoReader", return_value=reader):
            scan_live(updates, stop, capture=lambda: (frames.pop(0), GAME))

        seen = [updates.get_nowait() for _ in range(4)]
        self.assertEqual(seen[2].status, ANALYZING_ECHO)
        self.assertEqual(seen[3].echo.equipped_names, names)
        self.assertTrue(updates.empty())

    def test_gpu_error_disables_gpu_and_retries_the_frame_on_cpu(self):
        image, echo = sample(10)
        frames = [image] * 4
        stop = Mock(is_set=lambda: not frames)
        gpu, cpu = object(), object()
        reader = Mock(model=cpu, equipped_names=())
        reader.read.side_effect = [RuntimeError("DirectML failed"), echo]
        updates = queue.SimpleQueue()
        preference = threading.Event()
        preference.set()

        with (patch("wuwa_score.ocr.EchoReader", return_value=reader),
              patch("wuwa_score.ocr.load_gpu_model", return_value=gpu),
              self.assertLogs(level="ERROR")):
            scan_live(updates, stop, capture=lambda: (frames.pop(0), GAME), prefer_gpu=preference)

        self.assertEqual([args[0] for args, _ in reader.use_model.call_args_list], [gpu, cpu])
        self.assertEqual(updates.get_nowait(), GpuStatus(True))
        self.assertEqual(updates.get_nowait(), GpuStatus(True, active=True))
        self.assertIn("OCR", updates.get_nowait().status)
        self.assertEqual(updates.get_nowait(), GpuStatus(False))
        self.assertEqual(updates.get_nowait().echo, echo)
        self.assertTrue(updates.empty())
