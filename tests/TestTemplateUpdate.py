from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import update_xwuid_echo_templates as updater


def template(name):
    return {
        "name": name,
        "score_max": [50, 51, 52],
        "main_props": {"1": {"攻击%": 0.5}, "3": {}, "4": {}},
        "sub_props": {"暴击": 2},
        "skill_weight": [1, 0, 0, 0],
    }


class TestTemplateUpdate(unittest.TestCase):
    def test_reads_tracked_chinese_variant_and_conditions(self):
        conditions = [{"name": "试验"}]
        files = {
            "default/calc.json": template("角色-通用"),
            "1001/calc-试验.json": {**template("示例-试验"), "grade": {"SS": 45}},
            "1001/calc.json": template("示例-通用"),
            "1001/condition.json": conditions,
        }
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            tracked = []
            for name, record in files.items():
                relative = f"{updater.RESOURCE_PATH}/{name}"
                target = repo / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8-sig")
                tracked.append(relative)
            with patch.object(updater, "git", side_effect=["", "a" * 40, "\0".join(tracked)]):
                snapshot = updater.read_resources(repo)

        self.assertEqual("a" * 40, snapshot["source"]["commit"])
        self.assertEqual(["default", "试验"], list(snapshot["templates"]["1001"]))
        self.assertEqual(template("示例-试验"), snapshot["templates"]["1001"]["试验"])
        self.assertEqual({"1001": conditions}, snapshot["conditions"])

    def test_check_preserves_snapshot_and_unrelated_source_commit_is_ignored(self):
        previous = {
            "source": {"commit": "a" * 40},
            "templates": {"default": {"default": template("角色-通用")}},
            "conditions": {},
        }
        latest = {
            "source": {"commit": "b" * 40},
            "templates": {**previous["templates"], "1001": {"default": template("示例-通用")}},
            "conditions": {},
        }
        with tempfile.TemporaryDirectory() as directory:
            snapshot = Path(directory) / "templates.json"
            updater.write_snapshot(snapshot, previous)
            with patch.object(updater, "SNAPSHOT", snapshot), redirect_stdout(io.StringIO()) as output:
                with patch.object(updater, "read_resources", return_value=latest):
                    updater.main(["--check", "--no-fetch"])
                    self.assertEqual(previous, json.loads(snapshot.read_text(encoding="utf-8")))
                    self.assertIn("示例-通用", output.getvalue())
                    updater.main(["--no-fetch"])
                    self.assertEqual(latest, json.loads(snapshot.read_text(encoding="utf-8")))
                next_commit = {**latest, "source": {"commit": "c" * 40}}
                with patch.object(updater, "read_resources", return_value=next_commit):
                    updater.main(["--no-fetch"])
                    self.assertEqual(latest, json.loads(snapshot.read_text(encoding="utf-8")))

    def test_rejects_zero_score_maximum(self):
        with self.assertRaisesRegex(ValueError, "score_max"):
            updater.read_template({**template("示例-通用"), "score_max": [50, 0, 52]}, "calc.json")
