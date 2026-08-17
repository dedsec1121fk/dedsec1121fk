#!/usr/bin/env python3
"""Fetch profile data once and render all local profile cards without live card APIs."""

from __future__ import annotations

import argparse
import json
import os
import random
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PROFILE_DIR = ROOT / "profile"
DATA_PATH = PROFILE_DIR / "profile-data.json"
THEMES_PATH = ROOT / ".github" / "profile-themes.json"
GRAPHQL_URL = "https://api.github.com/graphql"
LOGIN = "dedsec1121fk"

QUERY = r'''
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    login
    name
    followers { totalCount }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, orderBy: {field: UPDATED_AT, direction: DESC}) {
      totalCount
      nodes {
        stargazerCount
        forkCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      totalIssueContributions
      totalPullRequestContributions
      totalPullRequestReviewContributions
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays { date contributionCount }
        }
      }
    }
  }
  rateLimit { cost remaining resetAt }
}
'''


def load_theme() -> tuple[str, dict[str, Any]]:
    config = json.loads(THEMES_PATH.read_text(encoding="utf-8"))
    current = config["current"]
    return current, config["themes"][current]


def blend_hex(first: str, second: str, second_weight: float) -> str:
    """Blend two six-digit colors while keeping generated cards GitHub-dark friendly."""
    second_weight = max(0.0, min(1.0, second_weight))
    a = tuple(int(first[i:i + 2], 16) for i in (0, 2, 4))
    b = tuple(int(second[i:i + 2], 16) for i in (0, 2, 4))
    return "".join(
        f"{round(left * (1 - second_weight) + right * second_weight):02x}"
        for left, right in zip(a, b)
    )


def palette(theme: dict[str, Any]) -> dict[str, str]:
    light = [str(value).lower() for value in theme["light_dots"]]
    dark = [str(value).lower() for value in theme["dark_dots"]]
    accent = str(theme["accent"]).lower()
    background = blend_hex(dark[0], "0d1117", 0.68)
    border = blend_hex(dark[1], "30363d", 0.72)
    return {
        "accent": accent,
        "background": background,
        "border": border,
        "text": light[0],
        "secondary": light[3],
        "highlight": light[4],
        "series1": accent,
        "series2": light[3],
        "series3": light[2],
        "series4": light[1],
        "series5": blend_hex(accent, light[0], 0.36),
        "series6": blend_hex(light[3], dark[1], 0.32),
    }


def parse_retry_after(headers: Any, attempt: int) -> int:
    retry_after = headers.get("Retry-After") if headers else None
    if retry_after:
        try:
            return max(1, min(1800, int(retry_after)))
        except ValueError:
            pass

    remaining = headers.get("X-RateLimit-Remaining") if headers else None
    reset = headers.get("X-RateLimit-Reset") if headers else None
    if remaining == "0" and reset:
        try:
            return max(1, min(1800, int(reset) - int(time.time()) + 5))
        except ValueError:
            pass

    # GitHub recommends backing off for secondary rate limits. Add jitter so
    # separate automation never wakes at the exact same second.
    base = min(900, 60 * (2 ** min(attempt - 1, 4)))
    return base + random.randint(3, 17)


def graphql_once(token: str, variables: dict[str, str]) -> dict[str, Any]:
    body = json.dumps({"query": QUERY, "variables": variables}).encode("utf-8")
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "dedsec-profile-static-cards/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        payload = json.load(response)
    if payload.get("errors"):
        raise RuntimeError(f"GraphQL returned errors: {payload['errors']!r}")
    return payload


def fetch_data() -> dict[str, Any]:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise SystemExit("GITHUB_TOKEN is required for the network refresh.")

    now = datetime.now(timezone.utc)
    variables = {
        "login": LOGIN,
        "from": (now - timedelta(days=365)).isoformat().replace("+00:00", "Z"),
        "to": now.isoformat().replace("+00:00", "Z"),
    }

    last_error: BaseException | None = None
    for attempt in range(1, 6):
        try:
            payload = graphql_once(token, variables)
            data = payload["data"]
            if not data.get("user"):
                raise RuntimeError(f"GitHub user {LOGIN!r} was not returned.")
            return normalize_data(data, now)
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code not in {403, 408, 425, 429, 500, 502, 503, 504}:
                raise
            delay = parse_retry_after(error.headers, attempt)
            print(f"GitHub HTTP {error.code}; respecting rate limit/backoff for {delay}s.")
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = error
            delay = min(300, 20 * (2 ** min(attempt - 1, 4))) + random.randint(1, 9)
            print(f"Temporary GitHub network error; retrying in {delay}s.")
            time.sleep(delay)

    raise RuntimeError(f"GitHub profile refresh deferred after safe retries: {last_error!r}")


def normalize_data(data: dict[str, Any], now: datetime) -> dict[str, Any]:
    user = data["user"]
    repos = user["repositories"]
    contrib = user["contributionsCollection"]

    language_sizes: dict[str, dict[str, Any]] = {}
    total_stars = 0
    total_forks = 0
    for repo in repos.get("nodes") or []:
        if not repo:
            continue
        total_stars += int(repo.get("stargazerCount") or 0)
        total_forks += int(repo.get("forkCount") or 0)
        for edge in (repo.get("languages") or {}).get("edges") or []:
            node = edge.get("node") or {}
            name = node.get("name")
            if not name:
                continue
            item = language_sizes.setdefault(
                name,
                {"name": name, "size": 0, "color": node.get("color") or "#8b949e"},
            )
            item["size"] += int(edge.get("size") or 0)

    days: list[dict[str, Any]] = []
    for week in contrib["contributionCalendar"].get("weeks") or []:
        days.extend(week.get("contributionDays") or [])
    days.sort(key=lambda item: item["date"])

    current_streak, longest_streak = calculate_streaks(days, now.date())
    langs = sorted(language_sizes.values(), key=lambda item: item["size"], reverse=True)

    return {
        "schema": 1,
        "generated_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "login": user.get("login") or LOGIN,
        "name": user.get("name") or LOGIN,
        "followers": int((user.get("followers") or {}).get("totalCount") or 0),
        "repositories": int(repos.get("totalCount") or 0),
        "stars": total_stars,
        "forks": total_forks,
        "contributions_1y": int(contrib["contributionCalendar"].get("totalContributions") or 0),
        "commits_1y": int(contrib.get("totalCommitContributions") or 0),
        "issues_1y": int(contrib.get("totalIssueContributions") or 0),
        "pull_requests_1y": int(contrib.get("totalPullRequestContributions") or 0),
        "reviews_1y": int(contrib.get("totalPullRequestReviewContributions") or 0),
        "private_contributions_1y": int(contrib.get("restrictedContributionsCount") or 0),
        "current_streak": current_streak,
        "longest_streak_1y": longest_streak,
        "languages": langs,
        "rate_limit": data.get("rateLimit") or {},
    }


def calculate_streaks(days: list[dict[str, Any]], today: date) -> tuple[int, int]:
    counts = {date.fromisoformat(item["date"]): int(item.get("contributionCount") or 0) for item in days}
    if not counts:
        return 0, 0

    ordered = sorted(counts)
    longest = 0
    run = 0
    previous: date | None = None
    for day in ordered:
        if previous is not None and day != previous + timedelta(days=1):
            run = 0
        if counts[day] > 0:
            run += 1
            longest = max(longest, run)
        else:
            run = 0
        previous = day

    anchor = today
    if counts.get(today, 0) == 0:
        anchor = today - timedelta(days=1)
    current = 0
    while counts.get(anchor, 0) > 0:
        current += 1
        anchor -= timedelta(days=1)
    return current, longest


FONT_FAMILY = "-apple-system,BlinkMacSystemFont,Segoe UI,Arial,sans-serif"


def svg_text(
    x: int | float,
    y: int | float,
    text: object,
    role: str,
    p: dict[str, str],
    *,
    anchor: str | None = None,
) -> str:
    styles = {
        "title": (17, 650, p["accent"], None),
        "label": (11, 450, p["text"], "0.76"),
        "value": (18, 650, p["text"], None),
        "accent_value": (18, 700, p["accent"], None),
        "small": (9, 450, p["text"], "0.52"),
        "rank": (30, 750, p["accent"], None),
        "rank_label": (9, 600, p["text"], "0.58"),
        "micro": (8, 550, p["text"], "0.56"),
    }
    if role not in styles:
        raise ValueError(f"Unknown SVG text role: {role}")

    size, weight, color, opacity = styles[role]
    attrs = [
        f'x="{x}"',
        f'y="{y}"',
        f'font-family="{FONT_FAMILY}"',
        f'font-size="{size}"',
        f'font-weight="{weight}"',
        f'fill="#{color}"',
    ]
    if anchor:
        attrs.append(f'text-anchor="{anchor}"')
    if opacity:
        attrs.append(f'opacity="{opacity}"')
    return f'  <text {" ".join(attrs)}>{escape(str(text))}</text>'


def svg_shell(width: int, height: int, title: str, content: str, p: dict[str, str]) -> str:
    title_text = escape(title)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{title_text}">
  <title>{title_text}</title>
  <rect x="0.75" y="0.75" width="{width - 1.5}" height="{height - 1.5}" rx="13" fill="#{p['background']}" stroke="#{p['border']}" stroke-width="1.5"/>
  <rect x="20" y="43" width="46" height="2" rx="1" fill="#{p['accent']}" opacity="0.88"/>
{svg_text(20, 31, title, "title", p)}
{content}
</svg>
'''


def _exponential_cdf(value: float) -> float:
    return 1 - 2 ** (-value)


def _log_normal_cdf(value: float) -> float:
    return value / (1 + value) if value > -1 else 0.0


def profile_rank(data: dict[str, Any]) -> tuple[str, float, float]:
    commits = max(0, int(data.get("commits_1y") or 0))
    prs = max(0, int(data.get("pull_requests_1y") or 0))
    issues = max(0, int(data.get("issues_1y") or 0))
    reviews = max(0, int(data.get("reviews_1y") or 0))
    stars = max(0, int(data.get("stars") or 0))
    followers = max(0, int(data.get("followers") or 0))

    weighted = (
        2 * _exponential_cdf(commits / 250)
        + 3 * _exponential_cdf(prs / 50)
        + _exponential_cdf(issues / 25)
        + _exponential_cdf(reviews / 2)
        + 4 * _log_normal_cdf(stars / 50)
        + _log_normal_cdf(followers / 10)
    )
    percentile = max(0.0, min(100.0, (1 - weighted / 12) * 100))
    thresholds = [1, 12.5, 25, 37.5, 50, 62.5, 75, 87.5, 100]
    levels = ["S", "A+", "A", "A-", "B+", "B", "B-", "C+", "C"]
    level = next((level for limit, level in zip(thresholds, levels) if percentile <= limit), "C")
    return level, percentile, 100 - percentile


def ring(
    cx: int | float,
    cy: int | float,
    radius: int | float,
    completion: float,
    color: str,
    p: dict[str, str],
    *,
    width: int = 5,
) -> str:
    completion = max(0.0, min(100.0, completion))
    circumference = 2 * 3.141592653589793 * float(radius)
    filled = circumference * completion / 100
    gap = circumference - filled
    return "\n".join(
        [
            f'  <circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="#{p["border"]}" stroke-width="{width}" opacity="0.62"/>',
            f'  <circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="#{color}" stroke-width="{width}" stroke-linecap="round" stroke-dasharray="{filled:.2f} {gap:.2f}" transform="rotate(-90 {cx} {cy})"/>',
        ]
    )


def metric_circle(cx: int, cy: int, radius: int, p: dict[str, str]) -> str:
    """Decorative circular metric container; no fake progress semantics."""
    return "\n".join(
        [
            f'  <circle cx="{cx}" cy="{cy}" r="{radius + 3}" fill="none" stroke="#{p["accent"]}" stroke-width="1" opacity="0.15"/>',
            f'  <circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="#{p["border"]}" stroke-width="4" opacity="0.78"/>',
            f'  <circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="#{p["accent"]}" stroke-width="2" opacity="0.90"/>',
        ]
    )


def stat_icon(kind: str, x: int, y: int, p: dict[str, str]) -> str:
    color = p["accent"]
    if kind == "star":
        return f'  <path d="M{x} {y-6} l2 4 4.5 .7 -3.3 3.2 .8 4.5 -4 -2.1 -4 2.1 .8 -4.5 -3.3 -3.2 4.5 -.7 z" fill="#{color}" opacity="0.92"/>'
    if kind == "commit":
        return "\n".join([
            f'  <line x1="{x-6}" y1="{y}" x2="{x+6}" y2="{y}" stroke="#{color}" stroke-width="1.7" opacity="0.9"/>',
            f'  <circle cx="{x}" cy="{y}" r="3" fill="#{p["background"]}" stroke="#{color}" stroke-width="1.7"/>',
        ])
    if kind == "followers":
        return "\n".join([
            f'  <circle cx="{x}" cy="{y-3}" r="2.8" fill="none" stroke="#{color}" stroke-width="1.6"/>',
            f'  <path d="M{x-5} {y+5} c.7-3.4 2.7-4.8 5-4.8 s4.3 1.4 5 4.8" fill="none" stroke="#{color}" stroke-width="1.6" stroke-linecap="round"/>',
        ])
    if kind == "repo":
        return "\n".join([
            f'  <rect x="{x-5}" y="{y-5}" width="10" height="12" rx="1.5" fill="none" stroke="#{color}" stroke-width="1.6"/>',
            f'  <line x1="{x-2}" y1="{y-1}" x2="{x+2.5}" y2="{y-1}" stroke="#{color}" stroke-width="1.4" stroke-linecap="round"/>',
        ])
    return f'  <circle cx="{x}" cy="{y}" r="3" fill="#{color}"/>'


def compact_metric(x: int, y: int, icon: str, label: str, value: object, p: dict[str, str]) -> str:
    return "\n".join(
        [
            stat_icon(icon, x + 7, y + 2, p),
            svg_text(x + 20, y, label, "label", p),
            svg_text(x + 20, y + 21, f"{int(value):,}", "accent_value", p),
        ]
    )


def render_stats(data: dict[str, Any], p: dict[str, str]) -> str:
    if data.get("seed"):
        content = "\n".join(
            [
                ring(354, 107, 43, 18, p["accent"], p, width=5),
                svg_text(354, 113, "…", "rank", p, anchor="middle"),
                svg_text(354, 136, "PROFILE RANK", "rank_label", p, anchor="middle"),
                svg_text(28, 88, "Refresh pending", "accent_value", p),
                svg_text(28, 112, "Authenticated profile data will populate this card.", "label", p),
            ]
        )
        return svg_shell(440, 190, "DedSec GitHub Stats", content, p)

    rank_level, rank_percentile, completion = profile_rank(data)
    parts = [
        compact_metric(24, 70, "star", "Stars", data["stars"], p),
        compact_metric(142, 70, "commit", "Commits (1y)", data["commits_1y"], p),
        compact_metric(24, 120, "followers", "Followers", data["followers"], p),
        compact_metric(142, 120, "repo", "Repositories", data["repositories"], p),
        ring(354, 108, 44, completion, p["accent"], p, width=5),
        svg_text(354, 108, rank_level, "rank", p, anchor="middle"),
        svg_text(354, 127, f"top {rank_percentile:.1f}%", "micro", p, anchor="middle"),
        svg_text(354, 166, "PROFILE RANK", "rank_label", p, anchor="middle"),
        svg_text(24, 177, f'{int(data["pull_requests_1y"]):,} pull requests  •  {int(data["issues_1y"]):,} issues  •  updated {str(data["generated_at_utc"])[11:16]} UTC', "small", p),
    ]
    return svg_shell(440, 190, "DedSec GitHub Stats", "\n".join(parts), p)


def render_streak(data: dict[str, Any], p: dict[str, str]) -> str:
    centers = (82, 220, 358)
    if data.get("seed"):
        parts: list[str] = [svg_text(416, 31, "LAST 365 DAYS", "micro", p, anchor="end")]
        for cx in centers:
            parts.append(metric_circle(cx, 102, 31, p))
        parts.extend([
            svg_text(220, 108, "…", "accent_value", p, anchor="middle"),
            svg_text(220, 155, "Refresh pending", "label", p, anchor="middle"),
        ])
        return svg_shell(440, 176, "GitHub Streak", "\n".join(parts), p)

    values = [
        (str(int(data["current_streak"])), "Current streak", "days"),
        (str(int(data["longest_streak_1y"])), "Longest streak", "days"),
        (f'{int(data["contributions_1y"]):,}', "Contributions", "1 year"),
    ]
    parts = [svg_text(416, 31, "LAST 365 DAYS", "micro", p, anchor="end")]
    for cx, (value, label, unit) in zip(centers, values):
        parts.append(metric_circle(cx, 101, 31, p))
        parts.append(svg_text(cx, 105, value, "accent_value", p, anchor="middle"))
        parts.append(svg_text(cx, 121, unit, "micro", p, anchor="middle"))
        parts.append(svg_text(cx, 157, label, "label", p, anchor="middle"))
    return svg_shell(440, 176, "GitHub Streak", "\n".join(parts), p)


def render_languages(data: dict[str, Any], p: dict[str, str]) -> str:
    if data.get("seed"):
        content = "\n".join(
            [
                ring(94, 121, 43, 18, p["accent"], p, width=12),
                svg_text(94, 126, "…", "accent_value", p, anchor="middle"),
                svg_text(188, 102, "Refresh pending", "accent_value", p),
                svg_text(188, 126, "Language totals will appear here.", "label", p),
            ]
        )
        return svg_shell(440, 210, "Most Used Languages", content, p)

    langs = data.get("languages") or []
    total = sum(int(item.get("size") or 0) for item in langs) or 1
    top = langs[:6]
    cx, cy, radius = 94, 125, 45
    circumference = 2 * 3.141592653589793 * radius
    colors = [p[f"series{i}"] for i in range(1, 7)]
    parts: list[str] = [
        f'  <circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="#{p["border"]}" stroke-width="13" opacity="0.62"/>'
    ]

    consumed = 0.0
    for index, item in enumerate(top):
        fraction = int(item["size"]) / total
        color = colors[index]
        seg = circumference * fraction
        remainder = max(0.0, circumference - seg)
        offset = -(circumference * consumed)
        parts.append(
            f'  <circle cx="{cx}" cy="{cy}" r="{radius}" fill="none" stroke="#{color}" stroke-width="13" '
            f'stroke-dasharray="{seg:.2f} {remainder:.2f}" stroke-dashoffset="{offset:.2f}" '
            f'transform="rotate(-90 {cx} {cy})"/>'
        )
        consumed += fraction

    dominant = top[0]["name"] if top else "—"
    dominant_pct = 100 * int(top[0]["size"]) / total if top else 0
    parts.extend(
        [
            svg_text(cx, cy - 1, f"{dominant_pct:.0f}%", "accent_value", p, anchor="middle"),
            svg_text(cx, cy + 16, dominant, "micro", p, anchor="middle"),
        ]
    )

    for idx, item in enumerate(top):
        pct = 100 * int(item["size"]) / total
        x = 184
        y = 72 + idx * 21
        color = colors[idx]
        parts.append(f'  <circle cx="{x}" cy="{y - 4}" r="4" fill="#{color}"/>')
        parts.append(svg_text(x + 12, y, item["name"], "label", p))
        parts.append(svg_text(416, y, f"{pct:.1f}%", "label", p, anchor="end"))

    parts.append(svg_text(20, 198, "Language share by bytes • owned, non-fork repositories", "small", p))
    return svg_shell(440, 210, "Most Used Languages", "\n".join(parts), p)

def render_all(data: dict[str, Any]) -> None:
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    _, theme = load_theme()
    p = palette(theme)
    (PROFILE_DIR / "stats.svg").write_text(render_stats(data, p), encoding="utf-8")
    (PROFILE_DIR / "streak.svg").write_text(render_streak(data, p), encoding="utf-8")
    (PROFILE_DIR / "top-langs.svg").write_text(render_languages(data, p), encoding="utf-8")


def seed_data() -> dict[str, Any]:
    return {
        "schema": 1,
        "seed": True,
        "generated_at_utc": "Waiting for first authenticated refresh",
        "login": LOGIN,
        "name": LOGIN,
        "followers": 0,
        "repositories": 0,
        "stars": 0,
        "forks": 0,
        "contributions_1y": 0,
        "commits_1y": 0,
        "issues_1y": 0,
        "pull_requests_1y": 0,
        "reviews_1y": 0,
        "private_contributions_1y": 0,
        "current_streak": 0,
        "longest_streak_1y": 0,
        "languages": [],
        "rate_limit": {},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["fetch-render", "render", "seed"])
    args = parser.parse_args()

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    if args.command == "fetch-render":
        data = fetch_data()
        DATA_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        render_all(data)
    elif args.command == "render":
        if not DATA_PATH.exists():
            raise SystemExit("profile/profile-data.json is missing; run fetch-render first.")
        render_all(json.loads(DATA_PATH.read_text(encoding="utf-8")))
    else:
        if not DATA_PATH.exists():
            DATA_PATH.write_text(json.dumps(seed_data(), indent=2) + "\n", encoding="utf-8")
        render_all(json.loads(DATA_PATH.read_text(encoding="utf-8")))


if __name__ == "__main__":
    main()
