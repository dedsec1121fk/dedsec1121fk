#!/usr/bin/env python3
import json
import os
import sys
import urllib.request
from collections import defaultdict

USERNAME = "dedsec1121fk"

# Colors (match screenshot cards)
CARD_BG = "#2b2f3a"
BORDER = "#c9d1d9"
TEXT = "#e6edf3"
TITLE = "#ff5fa2"
ACCENT = "#4fc3f7"
MUTED = "#b6bfca"
BG = CARD_BG

ASSETS_DIR = os.path.join(os.getcwd(), "assets")
os.makedirs(ASSETS_DIR, exist_ok=True)

API_GRAPHQL = "https://api.github.com/graphql"
API_REST = "https://api.github.com"

def gh_request(url, method="GET", data=None, headers=None):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Missing GITHUB_TOKEN.", file=sys.stderr)
        sys.exit(1)

    req_headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "github-actions-stats-cards",
        "Accept": "application/vnd.github+json",
    }
    if headers:
        req_headers.update(headers)

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(url, data=body, method=method, headers=req_headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")

def graphql(query, variables=None):
    payload = {"query": query, "variables": variables or {}}
    raw = gh_request(API_GRAPHQL, method="POST", data=payload, headers={"Content-Type": "application/json"})
    out = json.loads(raw)
    if "errors" in out:
        raise RuntimeError(out["errors"])
    return out["data"]

def rest(path):
    raw = gh_request(f"{API_REST}{path}", method="GET")
    return json.loads(raw)

def fmt(n: int) -> str:
    return f"{n:,}"

def esc(s: str) -> str:
    return (s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
             .replace('"',"&quot;").replace("'","&#39;"))

# Minimal inline "icons" (simple paths) to mimic card-style bullet icons.
# These are tiny and subtle; they render consistently.
ICON_PATHS = {
    "repo": "M4 4h12v16H4z M6 6h8v2H6z M6 10h8v2H6z M6 14h6v2H6z",
    "star": "M10 2l2.3 4.8L18 7.7l-4 3.9.9 5.6L10 14.8 5.1 17.2 6 11.6 2 7.7l5.7-.9z",
    "user": "M10 2a4 4 0 110 8 4 4 0 010-8zm0 10c4.4 0 8 2.2 8 5v1H2v-1c0-2.8 3.6-5 8-5z",
    "commit": "M10 4a3 3 0 100 6 3 3 0 000-6zm-8 3h5a5 5 0 0010 0h5v2h-5a5 5 0 01-10 0H2z",
}

def icon_svg(kind, x, y):
    # 18x18 icon box
    path = ICON_PATHS.get(kind, ICON_PATHS["repo"])
    return f'''
    <g transform="translate({x},{y})">
      <rect x="0" y="0" width="18" height="18" rx="5" fill="{ACCENT}" opacity="0.18"/>
      <path d="{path}" transform="translate(1,1) scale(0.85)" fill="{ACCENT}" opacity="0.95"/>
    </g>'''
def stats_card(title, items, width=700, height=260):
    """
    Screenshot-style stats card:
    - dark filled background
    - soft light border + inner divider line
    - left: icon + label + value rows
    - right: decorative grade ring (B+)
    NOTE: Only presentation; input data/logic unchanged.
    """
    pad = 22
    header_y = 52
    divider_y = 78

    # Row layout (left area)
    left_x = pad
    row_y0 = 118
    row_h = 30
    label_x = left_x + 34
    value_x = width - pad - 150  # keep room for ring

    # Ring layout
    ring_cx = width - pad - 78
    ring_cy = height // 2 + 10
    r = 44
    stroke_w = 10
    # fixed progress just for the look (not tied to stats)
    progress = 0.78

    parts = []
    # Title (pink)
    parts.append(f'<text x="{pad}" y="{header_y}" fill="{TITLE}" font-size="20" font-family="monospace">{esc(title)}</text>')
    parts.append(f'<line x1="{pad}" y1="{divider_y}" x2="{width-pad}" y2="{divider_y}" stroke="{BORDER}" stroke-opacity="0.35"/>')

    # Rows (single column like screenshot)
    for i, (kind, label, val) in enumerate(items):
        y = row_y0 + i * row_h
        parts.append(icon_svg(kind, left_x, y - 16))
        lbl = label if label.endswith(":") else (label + ":")
        parts.append(f'<text x="{label_x}" y="{y}" fill="{TEXT}" font-size="15" font-family="monospace">{esc(lbl)}</text>')
        parts.append(f'<text x="{value_x}" y="{y}" fill="{TEXT}" font-size="15" font-family="monospace" text-anchor="end">{esc(val)}</text>')

    # Grade ring (decorative)
    import math
    circ = 2 * math.pi * r
    dash = circ * progress
    gap = circ - dash
    parts.append(f'<circle cx="{ring_cx}" cy="{ring_cy}" r="{r}" fill="none" stroke="{BORDER}" stroke-opacity="0.18" stroke-width="{stroke_w}"/>')
    parts.append(
        f'<circle cx="{ring_cx}" cy="{ring_cy}" r="{r}" fill="none" '
        f'stroke="{TITLE}" stroke-width="{stroke_w}" stroke-linecap="round" '
        f'stroke-dasharray="{dash:.2f} {gap:.2f}" transform="rotate(-90 {ring_cx} {ring_cy})"/>'
    )
    parts.append(f'<text x="{ring_cx}" y="{ring_cy+6}" fill="{TEXT}" font-size="26" font-family="monospace" text-anchor="middle">B+</text>')

    return f"""<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>
  <rect x='1' y='1' width='{width-2}' height='{height-2}' rx='14' ry='14'
        fill='{BG}' stroke='{BORDER}' stroke-opacity='0.55' stroke-width='2'/>
  {''.join(parts)}
</svg>
"""

def langs_card(title, items, width=700, height=300):
    """Screenshot-style languages card:
    - dark filled background
    - big pink title
    - stacked usage bar
    - legend with colored dots and percentages (2 columns)
    """
    pad = 22
    header_y = 70
    divider_y = 98

    # Bar layout
    bar_x = pad
    bar_y = 140
    bar_w = width - 2*pad
    bar_h = 14
    radius = 7

    total = sum(v for _, v in items) or 1

    # Language colors approximating the screenshot
    palette = {
        'HTML': '#e34c26',
        'Python': '#3572A5',
        'CSS': '#563d7c',
        'JavaScript': '#f1e05a',
        'Shell': '#89e051',
    }
    def lang_color(name: str) -> str:
        return palette.get(name, '#8b949e')

    parts = []
    parts.append(f'<text x="{pad}" y="{header_y}" fill="{TITLE}" font-size="30" font-family="monospace">{esc(title)}</text>')
    parts.append(f'<line x1="{pad}" y1="{divider_y}" x2="{width-pad}" y2="{divider_y}" stroke="{BORDER}" stroke-opacity="0.35"/>')

    # Bar background
    parts.append(f'<rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="{radius}" fill="{BORDER}" opacity="0.12"/>')

    # Stacked segments
    x = bar_x
    for idx,(name,v) in enumerate(items):
        w = int(round(bar_w * (v/total)))
        # ensure last segment fills to end to avoid rounding gap
        if idx == len(items)-1:
            w = (bar_x + bar_w) - x
        if w <= 0:
            continue
        col = lang_color(name)
        # rounded ends only for first/last segment
        rx = radius if idx == 0 else 0
        ry = radius if idx == 0 else 0
        parts.append(f'<rect x="{x}" y="{bar_y}" width="{w}" height="{bar_h}" rx="{rx}" ry="{ry}" fill="{col}"/>')
        x += w

    # Legend (two columns)
    leg_y0 = 190
    row_h = 36
    col1_x = pad + 10
    col2_x = width//2 + 10

    for i,(name,v) in enumerate(items[:6]):
        pct = v/total*100.0
        cx = col1_x if i%2==0 else col2_x
        y = leg_y0 + (i//2)*row_h
        col = lang_color(name)
        parts.append(f'<circle cx="{cx}" cy="{y-5}" r="8" fill="{col}"/>')
        parts.append(f'<text x="{cx+18}" y="{y}" fill="{TEXT}" font-size="16" font-family="monospace">{esc(name)} {pct:0.2f}%</text>')

    return f"""<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>
  <rect x='1' y='1' width='{width-2}' height='{height-2}' rx='14' ry='14'
        fill='{BG}' stroke='{BORDER}' stroke-opacity='0.55' stroke-width='2'/>
  {''.join(parts)}
</svg>
"""
def main():
    # Basic user stats (REST)
    user = rest(f"/users/{USERNAME}")
    followers = int(user.get("followers", 0))
    following = int(user.get("following", 0))
    public_repos = int(user.get("public_repos", 0))

    # GraphQL: commits last year + repos stargazers + languages
    q = '''
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          totalCommitContributions
        }
        repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
          totalCount
          nodes {
            stargazerCount
            languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
              edges {
                size
                node { name }
              }
            }
          }
        }
      }
    }
    '''
    data = graphql(q, {"login": USERNAME})
    u = data["user"]
    commits = int(u["contributionsCollection"]["totalCommitContributions"])
    owned_repos = int(u["repositories"]["totalCount"])

    # IMPORTANT FIX: "Stars" = stars earned on your repos (sum of stargazerCount), NOT stars you starred.
    total_stars_earned = sum(int(r.get("stargazerCount", 0)) for r in u["repositories"]["nodes"])

    # Top languages aggregate
    agg = defaultdict(int)
    for repo in u["repositories"]["nodes"]:
        for edge in (repo.get("languages", {}).get("edges") or []):
            agg[edge["node"]["name"]] += int(edge["size"] or 0)
    top_langs = sorted(agg.items(), key=lambda x: x[1], reverse=True)[:8]

    stats_svg = stats_card(
        "FK's GitHub Stats",
        [
            ("repo", "Public repos", fmt(public_repos)),
            ("repo", "Owned repos", fmt(owned_repos)),
            ("star", "Stars (earned)", fmt(total_stars_earned)),
            ("user", "Followers", fmt(followers)),
            ("user", "Following", fmt(following)),
            ("commit", "Commits (last year)", fmt(commits)),
        ],
        height=250
    )

    langs_svg = langs_card("Most Used Languages", top_langs, height=300)

    with open(os.path.join(ASSETS_DIR, "github-stats.svg"), "w", encoding="utf-8") as f:
        f.write(stats_svg)
    with open(os.path.join(ASSETS_DIR, "top-langs.svg"), "w", encoding="utf-8") as f:
        f.write(langs_svg)

    print("Generated assets/github-stats.svg and assets/top-langs.svg")

if __name__ == "__main__":
    main()