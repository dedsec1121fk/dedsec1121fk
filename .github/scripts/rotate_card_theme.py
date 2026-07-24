#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

README = Path(__file__).resolve().parents[2] / "README.md"

PALETTES = [
    {"theme": "dracula", "badge": "6d28d9", "sponsor": "9333ea"},
    {"theme": "radical", "badge": "fe428e", "sponsor": "fe428e"},
    {"theme": "tokyonight", "badge": "7aa2f7", "sponsor": "7aa2f7"},
    {"theme": "merko", "badge": "abd200", "sponsor": "abd200"},
    {"theme": "gruvbox", "badge": "fabd2f", "sponsor": "fabd2f"},
    {"theme": "onedark", "badge": "61afef", "sponsor": "61afef"},
    {"theme": "cobalt", "badge": "2aa9ff", "sponsor": "2aa9ff"},
    {"theme": "synthwave", "badge": "e2e9ec", "sponsor": "ff7edb"},
    {"theme": "highcontrast", "badge": "f7e018", "sponsor": "f7e018"},
]


def replace_required(pattern: str, replacement: str, text: str, *, count: int = 0) -> str:
    updated, matches = re.subn(pattern, replacement, text, count=count)
    if matches == 0:
        raise RuntimeError(f"README pattern was not found: {pattern}")
    return updated


def main() -> None:
    text = README.read_text(encoding="utf-8")
    marker = re.search(r"<!--\s*card-theme:\s*([a-z0-9_-]+)\s*-->", text)
    current = marker.group(1) if marker else "dracula"

    themes = [palette["theme"] for palette in PALETTES]
    try:
        next_palette = PALETTES[(themes.index(current) + 1) % len(PALETTES)]
    except ValueError:
        next_palette = PALETTES[0]

    theme = next_palette["theme"]
    badge = next_palette["badge"]
    sponsor = next_palette["sponsor"]

    if marker:
        text = replace_required(
            r"<!--\s*card-theme:\s*[a-z0-9_-]+\s*-->",
            f"<!-- card-theme: {theme} -->",
            text,
            count=1,
        )
    else:
        text = text.replace("## GitHub Stats\n", f"## GitHub Stats\n\n<!-- card-theme: {theme} -->", 1)

    text = replace_required(r"([?&]theme=)[^&\"']+", rf"\g<1>{theme}", text)
    text = replace_required(
        r"(komarev\.com/ghpvc/\?[^\"']*?[?&]color=)[0-9A-Fa-f]+",
        rf"\g<1>{badge}",
        text,
        count=1,
    )
    text = replace_required(
        r"(GitHub%20Sponsors-Support%20%E2%9D%A4-)[0-9A-Fa-f]+(\?style=)",
        rf"\g<1>{sponsor}\g<2>",
        text,
        count=1,
    )

    README.write_text(text, encoding="utf-8")
    print(theme)


if __name__ == "__main__":
    main()
