#!/usr/bin/env python3
"""Keep all dynamic profile README colors synchronized."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / ".github" / "profile-themes.json"
README_PATH = ROOT / "README.md"


def load_config() -> dict[str, Any]:
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Unable to read {CONFIG_PATH}: {exc}") from exc

    current = config.get("current")
    rotation = config.get("rotation")
    themes = config.get("themes")
    if not isinstance(current, str) or not isinstance(rotation, list) or not isinstance(themes, dict):
        raise SystemExit("Invalid profile theme configuration structure.")
    if current not in themes:
        raise SystemExit(f"Unknown current theme: {current}")
    if not rotation or any(name not in themes for name in rotation):
        raise SystemExit("Theme rotation contains an unknown or missing theme.")
    return config


def select_theme(config: dict[str, Any], requested: str) -> str:
    themes = config["themes"]
    rotation = config["rotation"]
    current = config["current"]

    if requested == "auto":
        try:
            index = rotation.index(current)
        except ValueError:
            index = -1
        return rotation[(index + 1) % len(rotation)]

    if requested not in themes:
        available = ", ".join(["auto", *rotation])
        raise SystemExit(f"Unknown theme '{requested}'. Available values: {available}")
    return requested


def replace_exact(text: str, pattern: str, replacement: str, expected: int, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text)
    if count != expected:
        raise SystemExit(f"Expected {expected} {label} replacement(s), found {count}.")
    return updated


def update_readme(theme: str, theme_data: dict[str, Any]) -> None:
    try:
        text = README_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"Unable to read {README_PATH}: {exc}") from exc

    accent = theme_data["accent"]
    stats_theme = theme_data.get("stats_theme", theme)
    summary_theme = theme_data.get("summary_theme", theme)

    marker = f"<!-- profile-theme: {theme} -->"
    if re.search(r"<!-- profile-theme: [a-z0-9_-]+ -->", text):
        text = replace_exact(
            text,
            r"<!-- profile-theme: [a-z0-9_-]+ -->",
            marker,
            1,
            "theme marker",
        )
    else:
        text = marker + "\n\n" + text

    text = replace_exact(
        text,
        r"(github-readme-stats-fast\.vercel\.app/[^\"\s]*?[?&]theme=)[a-zA-Z0-9_-]+",
        rf"\g<1>{stats_theme}",
        3,
        "stats-card theme",
    )
    text = replace_exact(
        text,
        r"(github-profile-summary-cards\.vercel\.app/[^\"\s]*?[?&]theme=)[a-zA-Z0-9_-]+",
        rf"\g<1>{summary_theme}",
        1,
        "profile-summary theme",
    )
    text = replace_exact(
        text,
        r"(komarev\.com/ghpvc/\?[^\"\s]*?[?&]color=)[0-9a-fA-F]{6}",
        rf"\g<1>{accent}",
        1,
        "profile-view badge color",
    )
    text = replace_exact(
        text,
        r"(GitHub%20Sponsors-Support%20%E2%9D%A4-)[0-9a-fA-F]{6}(\?style=)",
        rf"\g<1>{accent}\g<2>",
        1,
        "Sponsors badge color",
    )

    README_PATH.write_text(text, encoding="utf-8")


def snake_outputs(theme_data: dict[str, Any]) -> str:
    accent = theme_data["accent"]
    light = ",".join(f"%23{color}" for color in theme_data["light_dots"])
    dark = ",".join(f"%23{color}" for color in theme_data["dark_dots"])
    return "\n".join(
        [
            f"dist/github-contribution-grid-snake.svg?color_snake=%23{accent}&color_dots={light}",
            f"dist/github-contribution-grid-snake-dark.svg?color_snake=%23{accent}&color_dots={dark}",
        ]
    )


def emit_outputs(theme: str, theme_data: dict[str, Any]) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        print(f"theme={theme}")
        print(f"accent={theme_data['accent']}")
        print(snake_outputs(theme_data))
        return

    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write(f"theme={theme}\n")
        handle.write(f"accent={theme_data['accent']}\n")
        handle.write("snake_outputs<<PROFILE_SNAKE_OUTPUTS\n")
        handle.write(snake_outputs(theme_data))
        handle.write("\nPROFILE_SNAKE_OUTPUTS\n")


def command_set(requested: str) -> None:
    config = load_config()
    selected = select_theme(config, requested)
    config["current"] = selected
    theme_data = config["themes"][selected]

    update_readme(selected, theme_data)
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    emit_outputs(selected, theme_data)


def command_emit() -> None:
    config = load_config()
    current = config["current"]
    emit_outputs(current, config["themes"][current])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    set_parser = subparsers.add_parser("set", help="Select a theme and update README colors.")
    set_parser.add_argument("theme", help="Theme name or 'auto' for the next rotation theme.")

    subparsers.add_parser("emit", help="Emit the current snake palette for GitHub Actions.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "set":
        command_set(args.theme)
    elif args.command == "emit":
        command_emit()
    else:
        raise SystemExit("Unsupported command.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
