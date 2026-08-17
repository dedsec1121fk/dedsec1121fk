#!/usr/bin/env python3
"""Recolor already-generated snake SVGs without querying GitHub again."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / ".github" / "profile-themes.json"


def colors(theme: dict) -> tuple[list[str], list[str]]:
    light = [theme["accent"], *theme["light_dots"]]
    dark = [theme["accent"], *theme["dark_dots"]]
    return light, dark


def replace_palette(path: Path, old: list[str], new: list[str]) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    placeholders: dict[str, str] = {}
    for idx, old_color in enumerate(old):
        token = f"__DEDSEC_COLOR_{idx}__"
        placeholders[token] = new[min(idx, len(new) - 1)]
        for form in {old_color.lower(), old_color.upper()}:
            text = text.replace(f"#{form}", token)
    for token, new_color in placeholders.items():
        text = text.replace(token, f"#{new_color}")
    path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-theme", required=True)
    parser.add_argument("--to-theme", required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()

    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    themes = config["themes"]
    if args.from_theme not in themes or args.to_theme not in themes:
        raise SystemExit("Unknown theme name.")

    old_light, old_dark = colors(themes[args.from_theme])
    new_light, new_dark = colors(themes[args.to_theme])
    replace_palette(args.directory / "github-contribution-grid-snake.svg", old_light, new_light)
    replace_palette(args.directory / "github-contribution-grid-snake-dark.svg", old_dark, new_dark)


if __name__ == "__main__":
    main()
