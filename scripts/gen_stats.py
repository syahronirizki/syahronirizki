#!/usr/bin/env python3
"""Generate the GitHub stat cards used by README.md.

Writes assets/stats.svg and assets/langs.svg from the GitHub GraphQL API.
Stdlib only. Run locally or from .github/workflows/stats.yml.

    GITHUB_TOKEN=<token> python3 scripts/gen_stats.py

A classic PAT with `repo` + `read:user` also counts private work; the
Actions-provided GITHUB_TOKEN only sees public activity.
"""

import json
import os
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from xml.sax.saxutils import escape

USER = os.environ.get("GH_USER", "syahronirizki")
TOKEN = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
OUT = Path(__file__).resolve().parent.parent / "assets"

BG_FROM, BG_VIA, BG_TO = "#0f0c29", "#302b63", "#24243e"
FG, MUTED, ACCENT = "#e6e6f0", "#9d97c9", "#7c6cf5"

QUERY = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    contributionsCollection {
      totalPullRequestContributions
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false) {
      totalCount
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""

# Flutter/Qt desktop runners and generated shells inflate these; they are not
# languages this profile is actually written in.
LANG_IGNORE = {"CMake", "C++", "Objective-C", "Swift", "Makefile", "Batchfile", "Shell"}

LANG_COLORS = {
    "TypeScript": "#3178c6",
    "Vue": "#41b883",
    "JavaScript": "#f1e05a",
    "Dart": "#00b4ab",
    "PHP": "#4F5D95",
    "HTML": "#e34c26",
    "Python": "#3572A5",
    "CSS": "#563d7c",
    "SCSS": "#c6538c",
}


def fetch():
    if not TOKEN:
        sys.exit("GITHUB_TOKEN (or GH_TOKEN) is required")
    body = json.dumps({"query": QUERY, "variables": {"login": USER}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": f"{USER}-profile-stats",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if payload.get("errors"):
        sys.exit(f"GraphQL error: {payload['errors']}")
    return payload["data"]["user"]


def streaks(days):
    """(current, longest) day streaks over the calendar window.

    Today is skipped while still empty so an unfinished day never resets a
    live streak.
    """
    counts = {d["date"]: d["contributionCount"] for d in days}
    longest = run = 0
    for day in sorted(counts):
        run = run + 1 if counts[day] > 0 else 0
        longest = max(longest, run)

    cursor = date.today()
    if counts.get(cursor.isoformat(), 0) == 0:
        cursor -= timedelta(days=1)
    current = 0
    while counts.get(cursor.isoformat(), 0) > 0:
        current += 1
        cursor -= timedelta(days=1)
    return current, longest


def collect(user):
    contrib = user["contributionsCollection"]
    cal = contrib["contributionCalendar"]
    days = [d for w in cal["weeks"] for d in w["contributionDays"]]
    current, longest = streaks(days)

    repos = user["repositories"]["nodes"]
    sizes = {}
    for repo in repos:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            if name in LANG_IGNORE:
                continue
            sizes[name] = sizes.get(name, 0) + edge["size"]
            LANG_COLORS.setdefault(name, edge["node"]["color"] or ACCENT)

    top = sorted(sizes.items(), key=lambda kv: -kv[1])[:6]
    total = sum(size for _, size in top) or 1

    return {
        "contributions": cal["totalContributions"],
        "private": contrib["restrictedContributionsCount"],
        "prs": contrib["totalPullRequestContributions"],
        "current": current,
        "longest": longest,
        "repos": user["repositories"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in repos),
        "followers": user["followers"]["totalCount"],
        "langs": [(n, s, s / total * 100) for n, s in top],
    }


def shell(width, height, body, title):
    """Common card chrome: gradient plate, border, type scale, a11y title."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" \
viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">
  <title>{escape(title)}</title>
  <defs>
    <linearGradient id="plate" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{BG_FROM}"/>
      <stop offset="55%" stop-color="{BG_VIA}"/>
      <stop offset="100%" stop-color="{BG_TO}"/>
    </linearGradient>
  </defs>
  <style>
    text {{ font-family: 'Segoe UI', Ubuntu, 'Helvetica Neue', Sans-Serif; }}
    .h {{ font-size: 15px; font-weight: 600; fill: {FG}; }}
    .k {{ font-size: 12.5px; fill: {MUTED}; }}
    .v {{ font-size: 15px; font-weight: 700; fill: {FG}; }}
    .s {{ font-size: 10.5px; fill: {MUTED}; }}
  </style>
  <rect width="{width}" height="{height}" rx="10" fill="url(#plate)"/>
  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="10" fill="none"
        stroke="{ACCENT}" stroke-opacity="0.35"/>
{body}
</svg>
"""


def render_stats(d):
    rows = [
        ("Contributions (last year)", f"{d['contributions']:,}"),
        ("Private contributions", f"{d['private']:,}"),
        ("Pull requests", f"{d['prs']:,}"),
        ("Current streak", f"{d['current']} day{'' if d['current'] == 1 else 's'}"),
        ("Longest streak (1y)", f"{d['longest']} day{'' if d['longest'] == 1 else 's'}"),
        ("Repositories owned", f"{d['repos']}"),
    ]
    body = [
        f'  <text x="22" y="34" class="h">{escape(USER)} &#183; activity</text>',
        f'  <line x1="22" y1="46" x2="398" y2="46" stroke="{ACCENT}" stroke-opacity="0.3"/>',
    ]
    for i, (label, value) in enumerate(rows):
        y = 74 + i * 25
        body.append(
            f'  <g><text x="22" y="{y}" class="k">{escape(label)}</text>'
            f'<text x="398" y="{y}" class="v" text-anchor="end">{escape(value)}</text></g>'
        )
    return shell(420, 232, "\n".join(body), f"{USER} GitHub activity")


def render_langs(d):
    body = [
        '  <text x="22" y="34" class="h">Most used languages</text>',
        f'  <line x1="22" y1="46" x2="338" y2="46" stroke="{ACCENT}" stroke-opacity="0.3"/>',
    ]

    # Stacked proportion bar.
    x, bar_w = 22.0, 316.0
    for name, _, pct in d["langs"]:
        w = bar_w * pct / 100
        body.append(
            f'  <rect x="{x:.1f}" y="64" width="{max(w - 2, 1):.1f}" height="10" '
            f'rx="5" fill="{LANG_COLORS.get(name, ACCENT)}"/>'
        )
        x += w

    for i, (name, _, pct) in enumerate(d["langs"]):
        col, row = i % 2, i // 2
        cx, cy = 22 + col * 160, 106 + row * 26
        body.append(
            f'  <g><circle cx="{cx + 5}" cy="{cy - 4}" r="5" '
            f'fill="{LANG_COLORS.get(name, ACCENT)}"/>'
            f'<text x="{cx + 18}" y="{cy}" class="k">{escape(name)}</text>'
            f'<text x="{cx + 146}" y="{cy}" class="s" text-anchor="end">{pct:.1f}%</text></g>'
        )

    body.append(
        '  <text x="22" y="214" class="s">Weighted by bytes across public and '
        'private repos.</text>'
    )
    return shell(360, 232, "\n".join(body), f"{USER} most used languages")


def main():
    data = collect(fetch())
    OUT.mkdir(exist_ok=True)
    (OUT / "stats.svg").write_text(render_stats(data), encoding="utf-8")
    (OUT / "langs.svg").write_text(render_langs(data), encoding="utf-8")
    print(json.dumps({k: v for k, v in data.items() if k != "langs"}, indent=2))
    print("langs:", ", ".join(f"{n} {p:.1f}%" for n, _, p in data["langs"]))


def _selfcheck():
    """Streak maths is the only non-obvious logic here; pin it."""
    today = date.today()

    def mk(offset, n):
        return {
            "date": (today - timedelta(days=offset)).isoformat(),
            "contributionCount": n,
        }

    # Three live days ending today.
    assert streaks([mk(0, 2), mk(1, 1), mk(2, 4), mk(3, 0), mk(4, 9)]) == (3, 3)
    # Empty today must not break a streak that ran through yesterday.
    assert streaks([mk(0, 0), mk(1, 1), mk(2, 1)]) == (2, 2)
    # A longer past run still wins "longest".
    assert streaks([mk(0, 1), mk(1, 0), mk(2, 1), mk(3, 1), mk(4, 1)]) == (1, 3)
    # No contributions at all.
    assert streaks([mk(0, 0), mk(1, 0)]) == (0, 0)
    print("selfcheck ok")


if __name__ == "__main__":
    if "--selfcheck" in sys.argv:
        _selfcheck()
    else:
        main()
