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


def normalized_unique(items: list[str]) -> set[str]:
    return {item.lower().lstrip("#") for item in items}


def detect_theme(directory: Path, themes: dict[str, dict]) -> str:
    """Detect which configured palette is currently present in the snake files."""
    light_path = directory / "github-contribution-grid-snake.svg"
    dark_path = directory / "github-contribution-grid-snake-dark.svg"
    if not light_path.exists() and not dark_path.exists():
        raise SystemExit("No contribution snake SVGs were found for automatic theme detection.")

    light_text = light_path.read_text(encoding="utf-8").lower() if light_path.exists() else ""
    dark_text = dark_path.read_text(encoding="utf-8").lower() if dark_path.exists() else ""

    scored: list[tuple[int, str]] = []
    for name, theme in themes.items():
        light, dark = colors(theme)
        light_score = sum(f"#{color}" in light_text for color in normalized_unique(light))
        dark_score = sum(f"#{color}" in dark_text for color in normalized_unique(dark))
        scored.append((light_score + dark_score, name))

    scored.sort(reverse=True)
    best_score, best_name = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else -1
    if best_score < 3 or best_score == second_score:
        details = ", ".join(f"{name}={score}" for score, name in scored)
        raise SystemExit(f"Unable to detect the current snake palette reliably ({details}).")

    print(f"Detected contribution snake palette: {best_name} (score {best_score}).")
    return best_name


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
    parser.add_argument("--from-theme", required=True, help="Theme name or 'auto'.")
    parser.add_argument("--to-theme", required=True)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()

    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    themes = config["themes"]
    if args.to_theme not in themes:
        raise SystemExit("Unknown destination theme name.")

    source = args.from_theme
    if source == "auto":
        source = detect_theme(args.directory, themes)
    elif source not in themes:
        raise SystemExit("Unknown source theme name.")

    if source == args.to_theme:
        print(f"Contribution snake already uses {args.to_theme}; no recolor is needed.")
        return

    old_light, old_dark = colors(themes[source])
    new_light, new_dark = colors(themes[args.to_theme])
    replace_palette(args.directory / "github-contribution-grid-snake.svg", old_light, new_light)
    replace_palette(args.directory / "github-contribution-grid-snake-dark.svg", old_dark, new_dark)
    print(f"Recolored contribution snake from {source} to {args.to_theme}.")


if __name__ == "__main__":
    main()
