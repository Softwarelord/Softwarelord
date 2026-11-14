"""Builds stats/stats.svg and stats/languages.svg from the owner's public AND
private GitHub data. Only totals are written out: no private repo names."""
import datetime as dt
import json
import os
import urllib.request
from html import escape

TOKEN = os.environ["GH_TOKEN"]
OUT = os.path.join(os.path.dirname(__file__), "..", "..", "stats")


def gql(query, **variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "User-Agent": "profile-stats"},
    )
    with urllib.request.urlopen(req) as r:
        body = json.load(r)
    if body.get("errors"):
        raise SystemExit(body["errors"])
    return body["data"]


user = gql("{ viewer { login name createdAt } }")["viewer"]

# Commit totals, all time (the API allows one year per query).
YEAR_Q = """query($from: DateTime!, $to: DateTime!) { viewer {
  contributionsCollection(from: $from, to: $to) {
    totalCommitContributions restrictedContributionsCount
    totalPullRequestContributions totalIssueContributions
    contributionCalendar { totalContributions } } } }"""
now = dt.datetime.now(dt.timezone.utc)
start = dt.datetime.fromisoformat(user["createdAt"].replace("Z", "+00:00"))
commits = contributions = prs = 0
this_year = 0
while start < now:
    end = min(start + dt.timedelta(days=365), now)
    c = gql(YEAR_Q, **{"from": start.isoformat(), "to": end.isoformat()})["viewer"]["contributionsCollection"]
    # Private commits come back as "restricted" contributions, so add them in.
    commits += c["totalCommitContributions"] + c["restrictedContributionsCount"]
    contributions += c["contributionCalendar"]["totalContributions"]
    prs += c["totalPullRequestContributions"]
    if end == now:
        this_year = c["contributionCalendar"]["totalContributions"]
    start = end

# Languages and repo count across every owned repo, private included.
REPO_Q = """query($after: String) { viewer { repositories(ownerAffiliations: OWNER, isFork: false,
  first: 100, after: $after) { totalCount pageInfo { hasNextPage endCursor }
  nodes { isPrivate languages(first: 20) { edges { size node { name color } } } } } } }"""
langs, after, repo_count, private_count = {}, None, 0, 0
while True:
    r = gql(REPO_Q, after=after)["viewer"]["repositories"]
    repo_count = r["totalCount"]
    for n in r["nodes"]:
        private_count += n["isPrivate"]
        for e in n["languages"]["edges"]:
            name = e["node"]["name"]
            size, color = langs.get(name, (0, e["node"]["color"] or "#8b949e"))
            langs[name] = (size + e["size"], color)
    if not r["pageInfo"]["hasNextPage"]:
        break
    after = r["pageInfo"]["endCursor"]

BG, BORDER, TITLE, TEXT, MUTED = "#0d1117", "#30363d", "#58a6ff", "#e6edf3", "#8b949e"
FONT = "font-family:'Segoe UI',Ubuntu,Helvetica,Arial,sans-serif"
os.makedirs(OUT, exist_ok=True)

rows = [
    ("Commits (incl. private work)", commits),
    ("Total contributions", contributions),
    ("Contributions in the last year", this_year),
    ("Repositories owned", repo_count),
    ("Private repositories", private_count),
    ("Public repositories", repo_count - private_count),
    ("Pull requests", prs),
]
h = 60 + 30 * len(rows)
items = "".join(
    f'<text x="25" y="{75 + i * 30}" style="{FONT};font-size:14px" fill="{TEXT}">{escape(k)}</text>'
    f'<text x="400" y="{75 + i * 30}" text-anchor="end" style="{FONT};font-size:14px;font-weight:700" fill="{TEXT}">{v:,}</text>'
    for i, (k, v) in enumerate(rows)
)
with open(os.path.join(OUT, "stats.svg"), "w", encoding="utf-8") as f:
    f.write(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="425" height="{h}" viewBox="0 0 425 {h}">'
        f'<rect x="0.5" y="0.5" width="424" height="{h - 1}" rx="6" fill="{BG}" stroke="{BORDER}"/>'
        f'<text x="25" y="38" style="{FONT};font-size:18px;font-weight:600" fill="{TITLE}">'
        f'{escape(user["name"] or user["login"])}\'s GitHub stats</text>{items}</svg>'
    )

top = sorted(langs.items(), key=lambda kv: -kv[1][0])[:8]
total = sum(s for _, (s, _) in top) or 1
bar, x = "", 25.0
for name, (size, color) in top:
    w = 375 * size / total
    bar += f'<rect x="{x:.2f}" y="55" width="{w:.2f}" height="10" fill="{color}"/>'
    x += w
legend = ""
for i, (name, (size, color)) in enumerate(top):
    lx, ly = 25 + (i % 2) * 195, 95 + (i // 2) * 26
    legend += (
        f'<circle cx="{lx + 5}" cy="{ly - 4}" r="5" fill="{color}"/>'
        f'<text x="{lx + 16}" y="{ly}" style="{FONT};font-size:13px" fill="{TEXT}">{escape(name)}'
        f'<tspan fill="{MUTED}"> {100 * size / total:.1f}%</tspan></text>'
    )
lh = 95 + 26 * ((len(top) + 1) // 2)
with open(os.path.join(OUT, "languages.svg"), "w", encoding="utf-8") as f:
    f.write(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="425" height="{lh}" viewBox="0 0 425 {lh}">'
        f'<rect x="0.5" y="0.5" width="424" height="{lh - 1}" rx="6" fill="{BG}" stroke="{BORDER}"/>'
        f'<text x="25" y="38" style="{FONT};font-size:18px;font-weight:600" fill="{TITLE}">Most used languages</text>'
        f'<clipPath id="c"><rect x="25" y="55" width="375" height="10" rx="5"/></clipPath>'
        f'<g clip-path="url(#c)">{bar}</g>{legend}</svg>'
    )

print(f"commits={commits} contributions={contributions} repos={repo_count} langs={[n for n, _ in top]}")
