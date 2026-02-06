#!/usr/bin/env python3
import json
import os
import sys
import urllib.request
from collections import defaultdict

USERNAME = "dedsec1121fk"

# Colors (card style like the screenshot)
# NOTE: Only visual styling constants are changed; logic/data stays the same.
BORDER = "#cfd6e4"   # soft light border
TEXT   = "#e6edf3"   # main text
TITLE  = "#ff5c9b"   # pink title
ICON   = "#4da3ff"   # blue accents/icons
MUTED  = "#a7b0bb"   # muted percent text
BG     = "#222733"   # dark card background

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
      <rect x="0" y="0" width="18" height="18" rx="5" fill="{ICON}" opacity="0.15"/>
      <path d="{path}" transform="translate(1,1) scale(0.85)" fill="{ICON}" opacity="0.9"/>
    </g>'''

def stats_card(title, items, width=600, height=220):
    # Layout inspired by github-readme-stats: title then two columns of stats.
    pad = 18
    header_y = 34
    col1_x = pad
    col2_x = width//2 + 10
    row_y0 = 78
    row_h = 30

    # split items into two columns
    mid = (len(items) + 1)//2
    left = items[:mid]
    right = items[mid:]

    parts = []
    parts.append(f'<text x="{pad}" y="{header_y}" fill="{TITLE}" font-size="20" font-family="monospace">{esc(title)}</text>')
    parts.append(f'<line x1="{pad}" y1="{header_y+10}" x2="{width-pad}" y2="{header_y+10}" stroke="{BORDER}" stroke-opacity="0.25"/>')

    def draw_col(col_items, x0, y0):
        out = []
        for i,(kind,label,val) in enumerate(col_items):
            y = y0 + i*row_h
            out.append(icon_svg(kind, x0, y-16))
            out.append(f'<text x="{x0+26}" y="{y}" fill="{TEXT}" font-size="15" font-family="monospace">{esc(label)}</text>')
            out.append(f'<text x="{x0+260}" y="{y}" fill="{ICON}" font-size="15" font-family="monospace" text-anchor="end">{esc(val)}</text>')
        return "".join(out)

    parts.append(draw_col(left, col1_x, row_y0))
    parts.append(draw_col(right, col2_x, row_y0))

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">
  <defs>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="3" stdDeviation="6" flood-color="#000000" flood-opacity="0.35"/>
    </filter>
  </defs>
  <rect x="1" y="1" width="{width-2}" height="{height-2}" rx="16" ry="16"
        fill="{BG}" stroke="{BORDER}" stroke-width="2" stroke-opacity="0.85" filter="url(#shadow)"/>
  {''.join(parts)}
</svg>
'''

def langs_card(title, items, width=600, height=260):
    pad = 18
    header_y = 34
    y = 80
    row_h = 22
    bar_x = pad + 210
    bar_w = width - bar_x - pad
    bar_h = 10

    total = sum(v for _, v in items) or 1
    parts = []
    parts.append(f'<text x="{pad}" y="{header_y}" fill="{TITLE}" font-size="20" font-family="monospace">{esc(title)}</text>')
    parts.append(f'<line x1="{pad}" y1="{header_y+10}" x2="{width-pad}" y2="{header_y+10}" stroke="{BORDER}" stroke-opacity="0.25"/>')

    for name, v in items:
        pct = v/total
        parts.append(f'<text x="{pad}" y="{y}" fill="{TEXT}" font-size="15" font-family="monospace">{esc(name)}</text>')
        # background bar
        parts.append(f'<rect x="{bar_x}" y="{y-12}" width="{bar_w}" height="{bar_h}" rx="5" fill="{ICON}" opacity="0.12"/>')
        # filled bar
        parts.append(f'<rect x="{bar_x}" y="{y-12}" width="{max(2, int(bar_w*pct))}" height="{bar_h}" rx="5" fill="{ICON}" opacity="0.55"/>')
        parts.append(f'<text x="{width-pad}" y="{y}" fill="{MUTED}" font-size="13" font-family="monospace" text-anchor="end">{pct*100:0.1f}%</text>')
        y += row_h

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">
  <defs>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="3" stdDeviation="6" flood-color="#000000" flood-opacity="0.35"/>
    </filter>
  </defs>
  <rect x="1" y="1" width="{width-2}" height="{height-2}" rx="16" ry="16"
        fill="{BG}" stroke="{BORDER}" stroke-width="2" stroke-opacity="0.85" filter="url(#shadow)"/>
  {''.join(parts)}
</svg>
'''

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
        "GitHub Stats",
        [
            ("repo", "Public repos", fmt(public_repos)),
            ("repo", "Owned repos", fmt(owned_repos)),
            ("star", "Stars (earned)", fmt(total_stars_earned)),
            ("user", "Followers", fmt(followers)),
            ("user", "Following", fmt(following)),
            ("commit", "Commits (last year)", fmt(commits)),
        ],
        height=220
    )

    langs_svg = langs_card("Top Languages", top_langs, height=260)

    with open(os.path.join(ASSETS_DIR, "github-stats.svg"), "w", encoding="utf-8") as f:
        f.write(stats_svg)
    with open(os.path.join(ASSETS_DIR, "top-langs.svg"), "w", encoding="utf-8") as f:
        f.write(langs_svg)

    print("Generated assets/github-stats.svg and assets/top-langs.svg")

if __name__ == "__main__":
    main()
