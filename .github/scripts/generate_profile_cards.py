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


def palette(theme: dict[str, Any]) -> dict[str, str]:
    return {
        "accent": theme["accent"].lower(),
        "background": theme["dark_dots"][0].lower(),
        "border": theme["dark_dots"][1].lower(),
        "text": theme["light_dots"][0].lower(),
        "secondary": theme["light_dots"][3].lower(),
        "highlight": theme["light_dots"][4].lower(),
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


def svg_shell(width: int, height: int, title: str, content: str, p: dict[str, str]) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">
  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="8" fill="#{p['background']}" stroke="#{p['border']}"/>
  <style>
    .title {{ font: 600 18px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; fill: #{p['accent']}; }}
    .label {{ font: 400 13px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; fill: #{p['text']}; }}
    .value {{ font: 600 18px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; fill: #{p['secondary']}; }}
    .small {{ font: 400 11px -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; fill: #{p['text']}; opacity: .78; }}
  </style>
  <text x="20" y="30" class="title">{escape(title)}</text>
{content}
</svg>\n'''


def render_stats(data: dict[str, Any], p: dict[str, str]) -> str:
    if data.get("seed"):
        content = (
            f'  <text x="20" y="82" class="value">Refresh pending</text>\n'
            f'  <text x="20" y="112" class="label">One authenticated daily refresh will populate this card.</text>\n'
            f'  <circle cx="410" cy="28" r="4" fill="#{p["highlight"]}"/>'
        )
        return svg_shell(440, 150, "DedSec GitHub Stats", content, p)

    rows = [
        ("Stars", data["stars"]),
        ("Repositories", data["repositories"]),
        ("Followers", data["followers"]),
        ("Contributions (1y)", data["contributions_1y"]),
    ]
    parts = []
    for idx, (label, value) in enumerate(rows):
        col = idx % 2
        row = idx // 2
        x = 22 + col * 210
        y = 67 + row * 58
        parts.append(f'  <text x="{x}" y="{y}" class="label">{escape(label)}</text>')
        parts.append(f'  <text x="{x}" y="{y + 24}" class="value">{value:,}</text>')
    parts.append(f'  <text x="20" y="164" class="small">Static daily card • {escape(data["generated_at_utc"])}</text>')
    return svg_shell(440, 180, "DedSec GitHub Stats", "\n".join(parts), p)


def render_streak(data: dict[str, Any], p: dict[str, str]) -> str:
    if data.get("seed"):
        content = (
            f'  <circle cx="55" cy="51" r="4" fill="#{p["highlight"]}"/>\n'
            f'  <text x="20" y="88" class="value">Refresh pending</text>\n'
            f'  <text x="20" y="116" class="label">Streak data is cached locally after the first daily refresh.</text>'
        )
        return svg_shell(440, 145, "GitHub Streak", content, p)

    parts = [
        f'  <circle cx="55" cy="51" r="4" fill="#{p["highlight"]}"/>',
        f'  <text x="55" y="82" text-anchor="middle" class="value">{data["current_streak"]}</text>',
        f'  <text x="55" y="105" text-anchor="middle" class="label">Current Streak</text>',
        f'  <text x="220" y="82" text-anchor="middle" class="value">{data["longest_streak_1y"]}</text>',
        f'  <text x="220" y="105" text-anchor="middle" class="label">Longest (1y)</text>',
        f'  <text x="385" y="82" text-anchor="middle" class="value">{data["contributions_1y"]:,}</text>',
        f'  <text x="385" y="105" text-anchor="middle" class="label">Contributions (1y)</text>',
        f'  <line x1="137" y1="58" x2="137" y2="112" stroke="#{p["border"]}"/>',
        f'  <line x1="302" y1="58" x2="302" y2="112" stroke="#{p["border"]}"/>',
        f'  <text x="20" y="144" class="small">Generated locally from one authenticated GitHub refresh</text>',
    ]
    return svg_shell(440, 160, "GitHub Streak", "\n".join(parts), p)


def render_languages(data: dict[str, Any], p: dict[str, str]) -> str:
    if data.get("seed"):
        content = (
            f'  <text x="20" y="82" class="value">Refresh pending</text>\n'
            f'  <text x="20" y="112" class="label">Language totals will be rendered from cached repository data.</text>\n'
            f'  <circle cx="410" cy="28" r="4" fill="#{p["highlight"]}"/>'
        )
        return svg_shell(440, 150, "Most Used Languages", content, p)

    langs = data.get("languages") or []
    total = sum(int(item.get("size") or 0) for item in langs) or 1
    top = langs[:6]
    parts: list[str] = []
    x0, y0, bar_w = 20, 52, 400
    cursor = x0
    for idx, item in enumerate(top):
        width = bar_w * int(item["size"]) / total
        color = item.get("color") or f"#{p['accent']}"
        if not str(color).startswith("#"):
            color = f"#{p['accent']}"
        parts.append(f'  <rect x="{cursor:.1f}" y="{y0}" width="{width:.1f}" height="10" fill="{escape(str(color))}"/>')
        cursor += width

    for idx, item in enumerate(top):
        pct = 100 * int(item["size"]) / total
        col = idx % 2
        row = idx // 2
        x = 24 + col * 205
        y = 88 + row * 29
        color = item.get("color") or f"#{p['accent']}"
        if not str(color).startswith("#"):
            color = f"#{p['accent']}"
        parts.append(f'  <circle cx="{x}" cy="{y - 4}" r="5" fill="{escape(str(color))}"/>')
        parts.append(f'  <text x="{x + 12}" y="{y}" class="label">{escape(item["name"])} {pct:.1f}%</text>')

    parts.append('  <text x="20" y="174" class="small">Language share by bytes across owned, non-fork repositories</text>')
    return svg_shell(440, 190, "Most Used Languages", "\n".join(parts), p)


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
