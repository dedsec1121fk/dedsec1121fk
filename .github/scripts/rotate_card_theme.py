#!/usr/bin/env python3
"""Keep every dynamic profile card on one synchronized color palette."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / ".github" / "profile-themes.json"
README_PATH = ROOT / "README.md"
STATS_PATH = ROOT / "profile" / "stats.svg"
STREAK_PATH = ROOT / "profile" / "streak.svg"
LANGUAGES_PATH = ROOT / "profile" / "top-langs.svg"
DATA_PATH = ROOT / "profile" / "profile-data.json"

HEX_COLOR = re.compile(r"^[0-9a-fA-F]{6}$")


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

    for theme_name, theme_data in themes.items():
        colors = [
            theme_data.get("accent"),
            *theme_data.get("light_dots", []),
            *theme_data.get("dark_dots", []),
        ]
        if not colors or any(not isinstance(color, str) or not HEX_COLOR.fullmatch(color) for color in colors):
            raise SystemExit(f"Theme '{theme_name}' contains an invalid six-digit hex color.")

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


def blend_hex(first: str, second: str, second_weight: float) -> str:
    second_weight = max(0.0, min(1.0, second_weight))
    a = tuple(int(first[i:i + 2], 16) for i in (0, 2, 4))
    b = tuple(int(second[i:i + 2], 16) for i in (0, 2, 4))
    return "".join(
        f"{round(left * (1 - second_weight) + right * second_weight):02x}"
        for left, right in zip(a, b)
    )


def card_palette(theme_data: dict[str, Any]) -> dict[str, str]:
    light = [str(value).lower() for value in theme_data["light_dots"]]
    dark = [str(value).lower() for value in theme_data["dark_dots"]]
    if len(light) < 5 or len(dark) < 2:
        raise SystemExit("Each theme needs at least five light colors and two dark colors.")

    return {
        "accent": str(theme_data["accent"]).lower(),
        "background": blend_hex(dark[0], "0d1117", 0.68),
        "border": blend_hex(dark[1], "30363d", 0.72),
        "text": light[0],
        "secondary": light[3],
        "highlight": light[4],
    }


def data_cache_token() -> str:
    """Return a stable token that changes whenever cached profile data changes."""
    try:
        data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "seed"

    generated = str(data.get("generated_at_utc") or "seed")
    token = re.sub(r"[^0-9A-Za-z]+", "", generated)
    return token or "seed"


def renderer_cache_token() -> str:
    """Change the image URL whenever the local card renderer itself changes."""
    renderer = ROOT / ".github" / "scripts" / "generate_profile_cards.py"
    try:
        digest = hashlib.sha256(renderer.read_bytes()).hexdigest()
    except OSError:
        return "renderer"
    return digest[:10]


def cache_key(theme: str, theme_data: dict[str, Any]) -> str:
    """Bust image caches for palette, profile data, and renderer changes."""
    palette = card_palette(theme_data)
    return f"{theme}-{palette['accent']}-{data_cache_token()}-{renderer_cache_token()}"


def expected_readme_values(theme: str, theme_data: dict[str, Any]) -> dict[str, str]:
    palette = card_palette(theme_data)
    version = cache_key(theme, theme_data)

    return {
        "marker": f"<!-- profile-theme: {theme} -->",
        "stats": (
            "https://raw.githubusercontent.com/dedsec1121fk/dedsec1121fk/main/"
            f"profile/stats.svg?v={version}"
        ),
        "streak": (
            "https://raw.githubusercontent.com/dedsec1121fk/dedsec1121fk/main/"
            f"profile/streak.svg?v={version}"
        ),
        "languages": (
            "https://raw.githubusercontent.com/dedsec1121fk/dedsec1121fk/main/"
            f"profile/top-langs.svg?v={version}"
        ),
        "views_counter": (
            "https://komarev.com/ghpvc/?username=dedsec1121fk&amp;style=pixel"
        ),
        "views": (
            "https://raw.githubusercontent.com/dedsec1121fk/dedsec1121fk/main/"
            f"profile/views.svg?v={version}"
        ),
        "sponsors": (
            "https://img.shields.io/badge/GitHub%20Sponsors-Support%20%E2%9D%A4-"
            f"{palette['accent']}?style=for-the-badge&logo=GitHub-Sponsors"
            f"&logoColor=white&v={version}"
        ),
        "snake_light": (
            "https://raw.githubusercontent.com/dedsec1121fk/dedsec1121fk/output/"
            f"github-contribution-grid-snake.svg?v={version}"
        ),
        "snake_dark": (
            "https://raw.githubusercontent.com/dedsec1121fk/dedsec1121fk/output/"
            f"github-contribution-grid-snake-dark.svg?v={version}"
        ),
    }


def skill_section_bounds(text: str) -> tuple[int, int]:
    """Locate the skills section without depending on a specific card URL."""
    skill_start = text.find("## Technologies & Skills")
    if skill_start == -1:
        raise SystemExit("README is missing the Technologies & Skills section.")

    streak = re.search(
        r'<p align="center">\s*<img[^>]*alt="GitHub Streak"[^>]*/>\s*</p>',
        text[skill_start:],
    )
    if not streak:
        raise SystemExit("Unable to locate the GitHub Streak card after Technologies & Skills.")
    return skill_start, skill_start + streak.start()


def update_skill_badges(text: str, theme_data: dict[str, Any]) -> str:
    """Synchronize all Technologies & Skills shields with the active palette."""
    palette = card_palette(theme_data)
    skill_start, skill_end = skill_section_bounds(text)

    before = text[:skill_start]
    section = text[skill_start:skill_end]
    after = text[skill_end:]

    badge_url = re.compile(r"https://img\.shields\.io/badge/[^\"\s]+")
    changed = 0

    def recolor(match: re.Match[str]) -> str:
        nonlocal changed
        url = match.group(0)
        if "style=flat-square" not in url:
            return url

        path, query = url.split("?", 1)
        prefix, old_color = path.rsplit("-", 1)
        if not HEX_COLOR.fullmatch(old_color):
            raise SystemExit(f"Unexpected skill badge color in URL: {url}")

        path = f"{prefix}-{palette['accent']}"
        if re.search(r"(?:^|&)logoColor=[^&]+", query):
            query = re.sub(
                r"((?:^|&)logoColor=)[^&]+",
                rf"\g<1>{palette['background']}",
                query,
            )
        else:
            query += f"&logoColor={palette['background']}"

        changed += 1
        return f"{path}?{query}"

    section = badge_url.sub(recolor, section)
    if changed == 0:
        raise SystemExit("No Technologies & Skills badges were found to recolor.")

    return before + section + after


def verify_skill_badges(readme: str, theme_data: dict[str, Any]) -> None:
    """Fail if any Technologies & Skills badge is outside the active palette."""
    palette = card_palette(theme_data)
    skill_start, skill_end = skill_section_bounds(readme)
    section = readme[skill_start:skill_end]
    urls = re.findall(r"https://img\.shields\.io/badge/[^\"\s]+", section)
    skill_urls = [url for url in urls if "style=flat-square" in url]
    if not skill_urls:
        raise SystemExit("No Technologies & Skills badges were found during verification.")

    for url in skill_urls:
        path, query = url.split("?", 1)
        color = path.rsplit("-", 1)[-1].lower()
        logo_match = re.search(r"(?:^|&)logoColor=([^&]+)", query)
        logo_color = logo_match.group(1).lower() if logo_match else ""
        if color != palette["accent"] or logo_color != palette["background"]:
            raise SystemExit(
                "Technologies & Skills badge is out of sync: "
                f"expected background #{palette['accent']} and logo #{palette['background']}, got {url}"
            )

    print(f"Verified {len(skill_urls)} Technologies & Skills badges on the active palette.")

def update_readme(theme: str, theme_data: dict[str, Any]) -> None:
    try:
        text = README_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"Unable to read {README_PATH}: {exc}") from exc

    values = expected_readme_values(theme, theme_data)

    if re.search(r"<!-- profile-theme: [a-z0-9_-]+ -->", text):
        text = replace_exact(
            text,
            r"<!-- profile-theme: [a-z0-9_-]+ -->",
            values["marker"],
            1,
            "theme marker",
        )
    else:
        text = values["marker"] + "\n\n" + text

    text = replace_exact(
        text,
        r'(<img\s+src=")[^"]+("\s+alt="DedSec GitHub Stats"\s*/>)',
        rf"\g<1>{values['stats']}\g<2>",
        1,
        "main stats card",
    )
    text = replace_exact(
        text,
        r'(<img\s+src=")[^"]+("\s+alt="GitHub Streak"\s*/>)',
        rf"\g<1>{values['streak']}\g<2>",
        1,
        "streak image source",
    )
    text = replace_exact(
        text,
        r'(<img\s+src=")[^"]+("\s+alt="Top Languages"\s*/>)',
        rf"\g<1>{values['languages']}\g<2>",
        1,
        "top-languages card",
    )
    text = replace_exact(
        text,
        r'(<img\s+src=")[^"]+("\s+alt="Profile views"\s*/>)',
        rf"\g<1>{values['views']}\g<2>",
        1,
        "profile-view badge",
    )
    if values["views_counter"] not in text:
        visible = f'  <img src="{values["views"]}" alt="Profile views" />'
        hidden = (
            f'  <img width="1" height="1" src="{values["views_counter"]}" alt="" />'
        )
        if visible not in text:
            raise SystemExit("Unable to locate the synchronized profile-view badge for counter insertion.")
        text = text.replace(visible, f"{hidden}\n{visible}", 1)
    text = replace_exact(
        text,
        r"https://img\.shields\.io/badge/GitHub%20Sponsors-Support%20%E2%9D%A4-[^\"\s]+",
        values["sponsors"],
        1,
        "Sponsors badge",
    )
    text = replace_exact(
        text,
        r"https://raw\.githubusercontent\.com/dedsec1121fk/dedsec1121fk/output/github-contribution-grid-snake\.svg(?:\?[^\"\s]*)?",
        values["snake_light"],
        1,
        "light contribution snake",
    )
    text = replace_exact(
        text,
        r"https://raw\.githubusercontent\.com/dedsec1121fk/dedsec1121fk/output/github-contribution-grid-snake-dark\.svg(?:\?[^\"\s]*)?",
        values["snake_dark"],
        2,
        "dark contribution snake",
    )

    text = update_skill_badges(text, theme_data)
    README_PATH.write_text(text, encoding="utf-8")


def verify_sync(theme: str, theme_data: dict[str, Any], require_streak: bool = True) -> None:
    try:
        readme = README_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"Unable to read {README_PATH}: {exc}") from exc

    values = expected_readme_values(theme, theme_data)
    expected_counts = {
        "marker": 1,
        "stats": 1,
        "streak": 1,
        "languages": 1,
        "views_counter": 1,
        "views": 1,
        "sponsors": 1,
        "snake_light": 1,
        "snake_dark": 2,
    }
    for name, expected_count in expected_counts.items():
        actual_count = readme.count(values[name])
        if actual_count != expected_count:
            raise SystemExit(
                f"README synchronization failed for {name}: expected {expected_count}, found {actual_count}."
            )

    verify_skill_badges(readme, theme_data)

    if require_streak:
        palette = card_palette(theme_data)
        card_specs = [
            (STATS_PATH, "stats", 3, "PROFILE RANK"),
            (STREAK_PATH, "streak", 6, "Contributions"),
            (LANGUAGES_PATH, "languages", 3, "Language share by bytes"),
        ]
        for path, label, minimum_circles, required_text in card_specs:
            try:
                svg = path.read_text(encoding="utf-8")
            except OSError as exc:
                raise SystemExit(f"Unable to read generated {label} card {path}: {exc}") from exc

            lowered = svg.lower()
            for role in ("background", "border", "accent", "text"):
                color = palette[role]
                if f"#{color}" not in lowered:
                    raise SystemExit(
                        f"Generated {label} card is missing the shared {role} color #{color}."
                    )

            circle_count = lowered.count("<circle")
            if circle_count < minimum_circles:
                raise SystemExit(
                    f"Generated {label} card lost its circular visual structure: "
                    f"expected at least {minimum_circles} circle elements, found {circle_count}."
                )
            if required_text not in svg:
                raise SystemExit(
                    f"Generated {label} card is missing its expected circular-layout marker: {required_text!r}."
                )

            # Parse as XML too, so malformed SVG never gets published.
            try:
                import xml.etree.ElementTree as ET
                ET.fromstring(svg)
            except Exception as exc:
                raise SystemExit(f"Generated {label} card is not valid SVG/XML: {exc}") from exc

        print("Verified circular stats rank, streak rings, and language donut structure.")

    print(f"All profile cards are synchronized to {theme} ({cache_key(theme, theme_data)}).")


def streak_options(theme_data: dict[str, Any]) -> str:
    palette = card_palette(theme_data)
    return (
        "user=dedsec1121fk"
        f"&background={palette['background']}"
        f"&border={palette['border']}"
        f"&stroke={palette['border']}"
        f"&ring={palette['accent']}"
        f"&fire={palette['highlight']}"
        f"&currStreakNum={palette['secondary']}"
        f"&sideNums={palette['text']}"
        f"&currStreakLabel={palette['accent']}"
        f"&sideLabels={palette['secondary']}"
        f"&dates={palette['text']}"
        "&border_radius=8"
        "&disable_animations=true"
    )


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


def emit_outputs(theme: str, theme_data: dict[str, Any], previous_theme: str | None = None) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    options = streak_options(theme_data)
    version = cache_key(theme, theme_data)
    if not output_path:
        print(f"theme={theme}")
        print(f"accent={theme_data['accent']}")
        print(f"cache_key={version}")
        if previous_theme is not None:
            print(f"previous_theme={previous_theme}")
        print(f"streak_options={options}")
        print(snake_outputs(theme_data))
        return

    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write(f"theme={theme}\n")
        handle.write(f"accent={theme_data['accent']}\n")
        handle.write(f"cache_key={version}\n")
        if previous_theme is not None:
            handle.write(f"previous_theme={previous_theme}\n")
        handle.write(f"streak_options={options}\n")
        handle.write("snake_outputs<<PROFILE_SNAKE_OUTPUTS\n")
        handle.write(snake_outputs(theme_data))
        handle.write("\nPROFILE_SNAKE_OUTPUTS\n")


def command_set(requested: str) -> None:
    config = load_config()
    previous = config["current"]
    selected = select_theme(config, requested)
    config["current"] = selected
    theme_data = config["themes"][selected]

    update_readme(selected, theme_data)
    CONFIG_PATH.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    emit_outputs(selected, theme_data, previous_theme=previous)


def command_emit() -> None:
    config = load_config()
    current = config["current"]
    update_readme(current, config["themes"][current])
    emit_outputs(current, config["themes"][current])


def command_verify() -> None:
    config = load_config()
    current = config["current"]
    verify_sync(current, config["themes"][current])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    set_parser = subparsers.add_parser("set", help="Select a theme and update README colors.")
    set_parser.add_argument("theme", help="Theme name or 'auto' for the next rotation theme.")

    subparsers.add_parser("emit", help="Emit the current shared card palette.")
    subparsers.add_parser("verify", help="Verify that every visible card uses the current palette.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "set":
        command_set(args.theme)
    elif args.command == "emit":
        command_emit()
    elif args.command == "verify":
        command_verify()
    else:
        raise SystemExit("Unsupported command.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
