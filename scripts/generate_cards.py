#!/usr/bin/env python3
"""Generate GitHub stats SVG cards into ./assets

This keeps your README fast & reliable by committing the SVGs into the repo.
Cards are fetched from the same endpoints you used in your styled README, so
they keep the exact same look (colors, layout, etc.).
"""

import os
import sys
import urllib.request

USERNAME = "dedsec1121fk"

ASSETS_DIR = os.path.join(os.getcwd(), "assets")
os.makedirs(ASSETS_DIR, exist_ok=True)

STATS_URL = (
    "https://github-readme-stats.vercel.app/api"
    f"?username={USERNAME}"
    "&show_icons=true"
    "&theme=transparent"
    "&border_color=9966ff"
    "&text_color=d0d8e0"
    "&title_color=9966ff"
    "&icon_color=e6d9ff"
)

LANGS_URL = (
    "https://github-readme-stats.vercel.app/api/top-langs/"
    f"?username={USERNAME}"
    "&layout=compact"
    "&theme=transparent"
    "&border_color=9966ff"
    "&text_color=d0d8e0"
    "&title_color=9966ff"
    "&icon_color=e6d9ff"
)

def fetch_svg(url: str) -> str:
    # GitHub Actions runner outbound is allowed; we also set a UA to avoid some blocks.
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "github-actions-stats-cards",
            "Accept": "image/svg+xml,text/plain,*/*",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read().decode("utf-8", errors="replace")

    if "<svg" not in data:
        raise RuntimeError(f"Response did not look like SVG for URL: {url}\n{data[:200]}")
    return data

def write(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)

def main() -> int:
    try:
        stats_svg = fetch_svg(STATS_URL)
        langs_svg = fetch_svg(LANGS_URL)
    except Exception as e:
        print(f"[generate_cards] ERROR: {e}", file=sys.stderr)
        return 1

    write(os.path.join(ASSETS_DIR, "github-stats.svg"), stats_svg)
    write(os.path.join(ASSETS_DIR, "top-langs.svg"), langs_svg)
    print("[generate_cards] Wrote assets/github-stats.svg and assets/top-langs.svg")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
