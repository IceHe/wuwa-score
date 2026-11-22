"""Update the standalone Echo templates from XutheringWavesUID-Resources.

Adapted from ok-wuthering-waves' slim branch template updater. See LICENSE.txt.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE_REPOSITORY = "https://cnb.cool/loping151/XutheringWavesUID-Resources.git"
RESOURCE_PATH = "XutheringWavesUID/resource/map/character"
SNAPSHOT = ROOT / "wuwa_score" / "templates.json"
SPARSE_PATTERNS = f"/{RESOURCE_PATH}/*/calc*.json\n/{RESOURCE_PATH}/*/condition.json\n"


def git(repo, *args, input_text=None):
    return subprocess.check_output(
        ["git", "-C", str(repo), *args], input=input_text, text=True, encoding="utf-8"
    ).strip()


def require_clean(repo):
    if git(repo, "status", "--porcelain"):
        raise RuntimeError(f"Resource checkout has local changes: {repo}")


def refresh_resources(repo):
    """Fetch only the scoring files into the updater's resource cache."""
    if not (repo / ".git").exists():
        if repo.exists() and any(repo.iterdir()):
            raise RuntimeError(f"Resource cache is not an empty Git checkout: {repo}")
        repo.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([
            "git", "clone", "--depth=1", "--filter=blob:none", "--sparse", "--branch", "main",
            SOURCE_REPOSITORY, str(repo),
        ], check=True)
    require_clean(repo)
    origin = git(repo, "remote", "get-url", "origin").rstrip("/")
    if origin.removesuffix(".git") != SOURCE_REPOSITORY.removesuffix(".git"):
        raise RuntimeError(f"Unexpected origin in resource cache: {repo}")
    git(repo, "fetch", "--depth=1", "origin", "main")
    git(repo, "sparse-checkout", "set", "--no-cone", "--stdin", input_text=SPARSE_PATTERNS)
    git(repo, "checkout", "--detach", "FETCH_HEAD")


def validate_weights(numbers, label, *, positive=False):
    for number in numbers:
        if (type(number) not in (int, float) or not math.isfinite(number)
                or number < 0 or (positive and number == 0)):
            raise ValueError(f"Invalid weight {number!r}: {label}")


def read_template(payload, path):
    if not isinstance(payload, dict) or not isinstance(payload.get("name"), str) or not payload["name"].strip():
        raise ValueError(f"Missing template name: {path}")
    main_props = payload["main_props"]
    if not isinstance(main_props, dict):
        raise ValueError(f"Invalid main_props: {path}")
    for cost in ("1", "3", "4"):
        weights = main_props[cost]
        if not isinstance(weights, dict):
            raise ValueError(f"Invalid main_props/{cost}: {path}")
        validate_weights(weights.values(), f"{path}: main_props/{cost}")
    sub_props = payload["sub_props"]
    if not isinstance(sub_props, dict):
        raise ValueError(f"Invalid sub_props: {path}")
    validate_weights(sub_props.values(), f"{path}: sub_props")

    for field, length in (("skill_weight", 4), ("score_max", 3)):
        values = payload[field]
        if not isinstance(values, list) or len(values) != length:
            raise ValueError(f"Invalid {field}: {path}")
        validate_weights(values, f"{path}: {field}", positive=field == "score_max")
    return {
        "name": payload["name"],
        "score_max": payload["score_max"],
        "main_props": {
            cost: dict(sorted(main_props[cost].items())) for cost in ("1", "3", "4")
        },
        "sub_props": dict(sorted(sub_props.items())),
        "skill_weight": payload["skill_weight"],
    }


def read_resources(repo):
    """Read the scoring files tracked at HEAD, including all variant templates."""
    require_clean(repo)
    commit = git(repo, "rev-parse", "HEAD")
    paths = git(repo, "ls-tree", "-rz", "--name-only", commit, "--", RESOURCE_PATH)
    templates, conditions = {}, {}
    for relative in paths.split("\0"):
        path = Path(relative)
        if path.parent.parent.as_posix() != RESOURCE_PATH:
            continue
        if path.name == "condition.json":
            condition = json.loads((repo / path).read_text(encoding="utf-8-sig"))
            if not isinstance(condition, list):
                raise ValueError(f"Invalid modal conditions: {relative}")
            conditions[path.parent.name] = condition
        elif path.name.startswith("calc") and path.suffix == ".json":
            if path.stem != "calc" and not path.stem.startswith("calc-"):
                raise ValueError(f"Unrecognized template filename: {relative}")
            variant = "default" if path.stem == "calc" else path.stem.removeprefix("calc-")
            payload = json.loads((repo / path).read_text(encoding="utf-8-sig"))
            variants = templates.setdefault(path.parent.name, {})
            if not variant or variant in variants:
                raise ValueError(f"Invalid or duplicate template variant: {relative}")
            variants[variant] = read_template(payload, path)

    if "default" not in templates:
        raise ValueError("Missing generic default template")
    for character, variants in templates.items():
        if "default" not in variants:
            raise ValueError(f"Missing calc.json for {character}")
    templates = {
        character: dict(sorted(variants.items()))
        for character, variants in sorted(templates.items())
    }
    return {
        "source": {"repository": SOURCE_REPOSITORY, "commit": commit},
        "templates": templates,
        "conditions": dict(sorted(conditions.items())),
    }


def differences(previous, current):
    def flatten(snapshot):
        templates = snapshot.get("templates", snapshot)
        return {(character, mode): record for character, variants in templates.items()
                for mode, record in variants.items()}

    old, new = flatten(previous), flatten(current)
    return {
        "added": [new[key]["name"] for key in sorted(new.keys() - old.keys())],
        "updated": [new[key]["name"] for key in sorted(new.keys() & old.keys()) if new[key] != old[key]],
        "removed": [old[key]["name"] for key in sorted(old.keys() - new.keys())],
        "conditions_changed": previous.get("conditions", {}) != current["conditions"],
    }


def write_snapshot(path, snapshot):
    """Replace the JSON atomically so the running scorer never reads a partial file."""
    content = json.dumps(snapshot, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with tempfile.TemporaryDirectory(dir=path.parent) as directory:
        temporary = Path(directory) / path.name
        temporary.write_text(content, encoding="utf-8", newline="\n")
        temporary.replace(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("resource_root", nargs="?", type=Path,
                        default=ROOT / "cache" / "xwuid-score-resources")
    parser.add_argument("--check", action="store_true", help="compare without writing the snapshot")
    parser.add_argument("--no-fetch", action="store_true", help="use an existing resource checkout")
    args = parser.parse_args(argv)
    repo = args.resource_root.resolve()
    if not args.no_fetch:
        refresh_resources(repo)
    snapshot = read_resources(repo)
    previous = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    changes = differences(previous, snapshot)

    count = sum(len(variants) for variants in snapshot["templates"].values())
    print(f"XW-UID resources: {snapshot['source']['commit']}; {count} templates")
    print(json.dumps(changes, ensure_ascii=False, indent=2))
    # Image-only upstream commits do not change the scoring snapshot.
    changed = "source" not in previous or any(changes.values())
    if args.check:
        return 0
    if changed:
        write_snapshot(SNAPSHOT, snapshot)
    print("Snapshot updated." if changed else "Snapshot already current.")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Update failed: {error}", file=sys.stderr)
        raise SystemExit(1)
