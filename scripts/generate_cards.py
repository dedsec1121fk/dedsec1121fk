#!/usr/bin/env python3
import json
import os
import sys
import urllib.request
from collections import defaultdict

USERNAME = "dedsec1121fk"

# Style (matches your existing colors)
BORDER = "#9966ff"
TEXT = "#d0d8e0"
TITLE = "#9966ff"
ICON = "#e6d9ff"
BG = "transparent"

ASSETS_DIR = os.path.join(os.getcwd(), "assets")
os.makedirs(ASSETS_DIR, exist_ok=True)

API_GRAPHQL = "https://api.github.com/graphql"
API_REST = "https://api.github.com"

def gh_request(url, method="GET", data=None, headers=None):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Missing GITHUB_TOKEN in environment.", file=sys.stderr)
        sys.exit(1)

    req_headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "github-actions-stats-cards",
        "Accept": "application/vnd.github+json",
    }
    if headers:
        req_headers.update(headers)

    if data is not None:
        body = json.dumps(data).encode("utf-8")
    else:
        body = None

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

def fmt(n):
    return f"{n:,}"

def svg_card(title, lines, width=600, height=180):
    # Simple, reliable SVG card (transparent bg, border, mono font)
    # Keeping style consistent with your theme colors.
    pad = 18
    line_h = 22
    y = 40
    text_lines = []
    text_lines.append(f'<text x="{pad}" y="{y}" fill="{TITLE}" font-size="20" font-family="monospace">{escape(title)}</text>')
    y += 28
    for label, value in lines:
        text_lines.append(
            f'<text x="{pad}" y="{y}" fill="{TEXT}" font-size="16" font-family="monospace">{escape(label)}: '
            f'<tspan fill="{ICON}">{escape(str(value))}</tspan></text>'
        )
        y += line_h

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">
  <rect x="1" y="1" width="{width-2}" height="{height-2}" rx="16" ry="16" fill="{BG}" stroke="{BORDER}" stroke-width="2"/>
  {''.join(text_lines)}
</svg>
'''

def svg_langs(title, items, width=600, height=240):
    pad = 18
    y = 40
    bar_x = pad
    bar_w = width - pad*2
    bar_y = y + 10
    bar_h = 10

    text = [f'<text x="{pad}" y="{y}" fill="{TITLE}" font-size="20" font-family="monospace">{escape(title)}</text>']
    y += 34

    total = sum(v for _, v in items) or 1
    # Bar (stacked)
    x = bar_x
    for name, v in items:
        w = int(bar_w * (v/total))
        if w < 2:
            continue
        text.append(f'<rect x="{x}" y="{bar_y}" width="{w}" height="{bar_h}" fill="{ICON}" opacity="0.45"/>')
        x += w

    y += 34
    # List
    for name, v in items:
        pct = (v/total)*100
        text.append(f'<text x="{pad}" y="{y}" fill="{TEXT}" font-size="16" font-family="monospace">'
                    f'{escape(name)}: <tspan fill="{ICON}">{pct:0.1f}%</tspan></text>')
        y += 22

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">
  <rect x="1" y="1" width="{width-2}" height="{height-2}" rx="16" ry="16" fill="{BG}" stroke="{BORDER}" stroke-width="2"/>
  {''.join(text)}
</svg>
'''

def escape(s):
    return (s.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;").replace("'","&#39;"))

def main():
    # Stats (REST + GraphQL for commits last year)
    user = rest(f"/users/{USERNAME}")
    repos = user.get("public_repos", 0)
    followers = user.get("followers", 0)
    following = user.get("following", 0)

    q = '''
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          totalCommitContributions
          restrictedContributionsCount
        }
        repositories(ownerAffiliations: OWNER, isFork: false) {
          totalCount
        }
        starredRepositories {
          totalCount
        }
      }
    }
    '''
    data = graphql(q, {"login": USERNAME})
    u = data["user"]
    commits = u["contributionsCollection"]["totalCommitContributions"]
    stars = u["starredRepositories"]["totalCount"]
    owned = u["repositories"]["totalCount"]

    stats_svg = svg_card(
        "GitHub Stats",
        [
            ("Public repos", fmt(repos)),
            ("Owned repos", fmt(owned)),
            ("Stars", fmt(stars)),
            ("Followers", fmt(followers)),
            ("Following", fmt(following)),
            ("Commits (last year)", fmt(commits)),
        ],
        height=210,
    )

    # Top languages (GraphQL, avoid many REST calls)
    q2 = '''
    query($login: String!) {
      user(login: $login) {
        repositories(first: 100, ownerAffiliations: OWNER, isFork: false, orderBy: {field: STARGAZERS, direction: DESC}) {
          nodes {
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
    data2 = graphql(q2, {"login": USERNAME})
    agg = defaultdict(int)
    for repo in data2["user"]["repositories"]["nodes"]:
        for edge in (repo.get("languages", {}).get("edges") or []):
            name = edge["node"]["name"]
            agg[name] += int(edge["size"] or 0)

    top = sorted(agg.items(), key=lambda x: x[1], reverse=True)[:8]
    langs_svg = svg_langs("Top Languages", top, height=240)

    with open(os.path.join(ASSETS_DIR, "github-stats.svg"), "w", encoding="utf-8") as f:
        f.write(stats_svg)
    with open(os.path.join(ASSETS_DIR, "top-langs.svg"), "w", encoding="utf-8") as f:
        f.write(langs_svg)

    print("Generated assets/github-stats.svg and assets/top-langs.svg")

if __name__ == "__main__":
    main()
