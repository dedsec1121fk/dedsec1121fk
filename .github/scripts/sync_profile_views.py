#!/usr/bin/env python3
"""Maintain a local, theme-aware profile-view badge without breaking view counting.

The visible badge is served from this repository so the profile never shows a broken
third-party image. A 1x1 Komarev pixel remains in README to count profile page hits.
The scheduled refresh reads the current total from Komarev and caches only the
numeric value; color rotations can then render the visible badge locally.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / ".github" / "profile-themes.json"
CACHE_PATH = ROOT / "profile" / "profile-views.json"
SVG_PATH = ROOT / "profile" / "views.svg"
USERNAME = "dedsec1121fk"
SOURCE_URL = f"https://komarev.com/ghpvc/?username={USERNAME}&style=flat-square"


def load_theme() -> tuple[str, dict[str, str]]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    theme = str(config["current"])
    data = config["themes"][theme]
    return theme, data


def load_cache() -> dict[str, object]:
    if not CACHE_PATH.exists():
        return {"count": None, "updated_at": None, "source": "komarev"}
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"count": None, "updated_at": None, "source": "komarev"}
    count = data.get("count")
    if not isinstance(count, int) or count < 0:
        count = None
    return {
        "count": count,
        "updated_at": data.get("updated_at"),
        "source": "komarev",
    }


def save_cache(count: int) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "count": count,
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": "komarev",
    }
    CACHE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def fetch_count() -> int:
    request = urllib.request.Request(
        SOURCE_URL,
        headers={
            "User-Agent": "dedsec1121fk-profile-refresh/1.0",
            "Accept": "image/svg+xml,image/*;q=0.9,*/*;q=0.8",
            "Cache-Control": "no-cache",
        },
    )
    last_error: Exception | None = None
    for attempt, delay in enumerate((0, 3, 8, 15), start=1):
        if delay:
            time.sleep(delay)
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                if response.status != 200:
                    raise RuntimeError(f"HTTP {response.status}")
                raw = response.read(256_000)
            root = ET.fromstring(raw)
            if not root.tag.lower().endswith("svg"):
                raise RuntimeError("response is not SVG")

            candidates: list[int] = []
            for element in root.iter():
                if element.text:
                    text = element.text.strip()
                    if re.fullmatch(r"[0-9][0-9,]*", text):
                        candidates.append(int(text.replace(",", "")))
            if not candidates:
                raise RuntimeError("profile-view count was not present in the SVG")
            return max(candidates)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ET.ParseError, RuntimeError) as exc:
            last_error = exc
            print(f"Profile-view refresh attempt {attempt}/4 failed: {exc}", file=sys.stderr)

    raise RuntimeError(f"Komarev profile-view refresh failed after 4 attempts: {last_error}")


def esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_badge(count: int | None) -> None:
    _, theme = load_theme()
    accent = str(theme["accent"]).lstrip("#").lower()
    text_color = str(theme.get("text", "ffffff")).lstrip("#").lower()
    background = str(theme.get("background", "161921")).lstrip("#").lower()
    border = str(theme.get("border", "30363d")).lstrip("#").lower()

    label = "Profile views"
    value = f"{count:,}" if count is not None else "—"
    label_width = 86
    value_width = max(42, 18 + 7 * len(value))
    total_width = label_width + value_width
    label_x = label_width / 2
    value_x = label_width + value_width / 2
    title_value = value if count is not None else "waiting for counter service"

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="20" role="img" aria-label="Profile views: {esc(title_value)}">
  <title>Profile views: {esc(title_value)}</title>
  <rect width="{total_width}" height="20" rx="4" fill="#{border}"/>
  <rect x="1" y="1" width="{label_width - 1}" height="18" rx="3" fill="#{background}"/>
  <rect x="{label_width}" y="1" width="{value_width - 1}" height="18" rx="3" fill="#{accent}"/>
  <path d="M{label_width} 1h3v18h-3z" fill="#{accent}"/>
  <g fill="#{text_color}" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">
    <text x="{label_x:.1f}" y="14">{label}</text>
    <text x="{value_x:.1f}" y="14" font-weight="700">{esc(value)}</text>
  </g>
</svg>
'''
    ET.fromstring(svg)
    SVG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SVG_PATH.write_text(svg, encoding="utf-8")
    print(f"Rendered {SVG_PATH.relative_to(ROOT)} with count {value}.")


def command_refresh() -> int:
    cache = load_cache()
    try:
        count = fetch_count()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        count = cache.get("count")
        if count is None:
            print("No cached profile-view total exists yet; rendering a non-broken pending badge.", file=sys.stderr)
        else:
            print(f"Keeping cached profile-view total {count:,}.", file=sys.stderr)
    else:
        save_cache(count)
        print(f"Cached profile-view total: {count:,}.")

    render_badge(count if isinstance(count, int) else None)
    return 0


def command_render() -> int:
    cache = load_cache()
    count = cache.get("count")
    render_badge(count if isinstance(count, int) else None)
    return 0


def command_verify() -> int:
    theme_name, theme = load_theme()
    if not SVG_PATH.exists():
        raise SystemExit("profile/views.svg is missing")
    svg = SVG_PATH.read_text(encoding="utf-8")
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as exc:
        raise SystemExit(f"profile/views.svg is invalid XML: {exc}") from exc
    if not root.tag.lower().endswith("svg"):
        raise SystemExit("profile/views.svg is not an SVG document")
    accent = f"#{str(theme['accent']).lstrip('#').lower()}"
    if accent not in svg.lower():
        raise SystemExit(f"profile/views.svg does not match active theme {theme_name} ({accent})")
    if "Profile views" not in svg:
        raise SystemExit("profile/views.svg is missing its label")
    print(f"Verified local profile-view badge for {theme_name}.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("refresh", "render", "verify"))
    args = parser.parse_args()
    if args.command == "refresh":
        return command_refresh()
    if args.command == "render":
        return command_render()
    return command_verify()


if __name__ == "__main__":
    raise SystemExit(main())
