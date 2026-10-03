"""Update the GitHub profile README with current account statistics."""

import calendar
import html
import json
import os
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

USER = "serdire"
JOINED_YEAR = 2026
BIRTHDAY = date(2000, 1, 1)
README_PATH = Path(__file__).resolve().with_name("README.md")
TOKEN = os.environ.get("ACCESS_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
OUTPUTS = {
    "dark": Path(__file__).resolve().with_name("dark_mode.svg"),
    "light": Path(__file__).resolve().with_name("light_mode.svg"),
}
WIDTH = 56

ART = r"""
                 ++==---
            +==---------:-:::
          +==------::::::..... .
        *===----:::::...::::..   :#
       +==-=========++++++++==:.  .#
      =--=+*#%%######******++++-:  +
      -=*#%%%%%%#####*******+++=-:.=
      =*%%@@@@%%%######******+++=-:-
      +#%%##*+++*###**+----===+++=--#
      +#%#+===::-+##*=::::::-==++=--=*
    %#*#%#*+*+-=+#%%*=---:---=++++==+=   #
    %#*#%%%%%###%%%%*+++++++***+++=-=+##**
    @#+#%%%%%%%%%%%#*++++***+++++++==*###
     %###%%%%#####++=-=+++**+++++++++
      %%########%%#+++++++**++==+++*
        ##*###**#**++====++*++++++
         *##%#**##*++++++++*+++==*
          *###%%%##******+++++===+
           **##%%%#*****++====-==
         #+#*+++++=====------==++.
         ..%##*+=------:---===++=-.
     #+   :%%%%#*+=----====+++++=-.
 *+    .  :#%%###*++====++++*+++=-
       .  :+######****++*****+++=
          :+**#####************=
           :+***####***##****+:
             -+*##########+==.
               .=*#####*=.
"""

PALETTES = {
    "dark": {
        "bg": "#0d1117", "border": "#30363d", "art": "#8b949e",
        "h": "#58a6ff", "k": "#ffa657", "v": "#c9d1d9",
        "d": "#484f58", "g": "#3fb950", "r": "#f85149",
    },
    "light": {
        "bg": "#ffffff", "border": "#d0d7de", "art": "#57606a",
        "h": "#0969da", "k": "#953800", "v": "#24292f",
        "d": "#afb8c1", "g": "#1a7f37", "r": "#cf222e",
    },
}


def gh(payload, token=None):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "profile-readme-stats",
    }
    auth = (token or TOKEN).strip()
    if auth:
        headers["Authorization"] = "Bearer " + auth

    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not connect to the GitHub API: {exc.reason}") from exc

    if result.get("errors"):
        raise RuntimeError(f"GitHub GraphQL error: {result['errors']}")
    return result["data"]


def graphql(query, variables=None, token=None):
    return gh({"query": query, "variables": variables or {}}, token)


def fetch_stats():
    if not TOKEN:
        raise RuntimeError(
            "No GitHub token is configured. Set ACCESS_TOKEN or GITHUB_TOKEN "
            "in the environment, then run this script again."
        )

    year_fields = "\n".join(
        f'y{year}: contributionsCollection(from: "{year}-01-01T00:00:00Z", '
        f'to: "{year + 1}-01-01T00:00:00Z") '
        "{ totalCommitContributions restrictedContributionsCount }"
        for year in range(JOINED_YEAR, datetime.now(timezone.utc).year + 1)
    )
    contributions = graphql(
        f'query {{ user(login: "{USER}") {{ {year_fields} }} }}'
    )["user"]
    commits = sum(
        item["totalCommitContributions"] + item["restrictedContributionsCount"]
        for item in contributions.values()
    )

    repo_query = """
    query($cursor: String) {
      user(login: "serdire") {
        id
        followers { totalCount }
        repositories(first: 100, ownerAffiliations: OWNER, after: $cursor) {
          totalCount
          nodes { name stargazerCount isFork }
          pageInfo { hasNextPage endCursor }
        }
        repositoriesContributedTo(
          first: 1
          contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY]
        ) {
          totalCount
        }
      }
    }"""
    repos = []
    cursor = None
    while True:
        user = graphql(repo_query, {"cursor": cursor})["user"]
        connection = user["repositories"]
        repos.extend(connection["nodes"])
        if not connection["pageInfo"]["hasNextPage"]:
            break
        cursor = connection["pageInfo"]["endCursor"]

    stats = {
        "followers": user["followers"]["totalCount"],
        "repos": connection["totalCount"],
        "contributed": user["repositoriesContributedTo"]["totalCount"],
        "stars": sum(repo["stargazerCount"] for repo in repos),
        "commits": commits,
    }
    stats.update(
        loc(
            [repo["name"] for repo in repos if not repo["isFork"]],
            user["id"],
        )
    )
    return stats


LOC_QUERY = """
query($owner: String!, $name: String!, $id: ID!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    defaultBranchRef {
      target {
        ... on Commit {
          history(first: 100, author: {id: $id}, after: $cursor) {
            pageInfo { hasNextPage endCursor }
            nodes { additions deletions }
          }
        }
      }
    }
  }
}"""


def loc(repo_names, user_id):
    additions = deletions = 0
    for name in repo_names:
        cursor = None
        while True:
            repo = graphql(
                LOC_QUERY,
                {
                    "owner": USER,
                    "name": name,
                    "id": user_id,
                    "cursor": cursor,
                },
            )["repository"]
            if repo is None or repo["defaultBranchRef"] is None:
                break
            history = repo["defaultBranchRef"]["target"]["history"]
            additions += sum(commit["additions"] for commit in history["nodes"])
            deletions += sum(commit["deletions"] for commit in history["nodes"])
            if not history["pageInfo"]["hasNextPage"]:
                break
            cursor = history["pageInfo"]["endCursor"]
    return {
        "loc_add": additions,
        "loc_del": deletions,
        "loc": additions - deletions,
    }


def age(birthday, today):
    years = today.year - birthday.year - (
        (today.month, today.day) < (birthday.month, birthday.day)
    )
    months = (today.month - birthday.month - (today.day < birthday.day)) % 12
    if today.day >= birthday.day:
        days = today.day - birthday.day
    else:
        previous_month_year, previous_month = (
            (today.year, today.month - 1) if today.month > 1
            else (today.year - 1, 12)
        )
        days = calendar.monthrange(previous_month_year, previous_month)[1] - birthday.day + today.day
    return years, months, days


def kv(key, value, width=WIDTH):
    dots = "." * max(width - len(key) - len(str(value)) - 3, 1)
    return [(f"{key}: ", "k"), (dots + " ", "d"), (str(value), "v")]


def kv2(key1, value1, key2, value2):
    return kv(key1, value1, 30) + [(" | ", "d")] + kv(key2, value2, 23)


def rule(title):
    label = f"─ {title} "
    return [(label, "h"), ("─" * (WIDTH - len(label)), "d")]


def info_lines(stats):
    years, months, days = age(BIRTHDAY, date.today())
    number = lambda value: f"{value:,}"
    return [
        [(f"{USER}@github ", "h"), ("─" * (WIDTH - len(USER) - 8), "d")],
        [],
        kv("OS", "Windows"),
        kv("Uptime", f"{years} years, {months} months, {days} days"),
        kv("Host", "Trimble"),
        kv("Phishing", "Security Researcher"),
        kv("IDE", "Claude Code, Cursor, VS Code"),
        [],
        kv("Languages.Programming", "Python, Java, C#, TypeScript"),
        kv("Languages.Real", "Hindi, English"),
        kv("Hobbies", "Fishing"),
        [],
        rule("Contact"),
        kv("Email", "yashmahesh833@hotmail.com"),
        kv("LinkedIn", "in/yash-mahesh"),
        [],
        rule("GitHub Stats"),
        kv2("Repos", f"{stats['repos']} {{Contributed: {stats['contributed']}}}", "Stars", number(stats["stars"])),
        kv2("Commits", number(stats["commits"]), "Followers", number(stats["followers"])),
        [
            ("Lines of Code: ", "k"), (number(stats["loc"]), "v"), (" ( ", "d"),
            (number(stats["loc_add"]) + "++", "g"), (", ", "d"),
            (number(stats["loc_del"]) + "--", "r"), (" )", "d"),
        ],
    ]


def render(mode, stats):
    palette = PALETTES[mode]
    output = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="840" height="500" '
        'viewBox="0 0 840 500" font-family="Consolas, Menlo, monospace" '
        'font-size="13px">',
        f'<rect x="0.5" y="0.5" width="839" height="499" rx="10" '
        f'fill="{palette["bg"]}" stroke="{palette["border"]}"/>',
    ]
    for index, line in enumerate(ART.strip("\n").split("\n")):
        output.append(
            f'<text x="25" y="{40 + index * 15}" fill="{palette["art"]}" '
            f'xml:space="preserve">{html.escape(line)}</text>'
        )
    for index, segments in enumerate(info_lines(stats)):
        if not segments:
            continue
        spans = "".join(
            f'<tspan fill="{palette[color]}">{html.escape(text)}</tspan>'
            for text, color in segments
        )
        output.append(
            f'<text x="390" y="{45 + index * 21}" xml:space="preserve">'
            f"{spans}</text>"
        )
    output.append("</svg>")
    return "\n".join(output)


def write_svgs(stats):
    for mode, path in OUTPUTS.items():
        path.write_text(render(mode, stats), encoding="utf-8")


def selfcheck():
    example = {
        "followers": 12,
        "repos": 4,
        "contributed": 3,
        "stars": 27,
        "commits": 100,
        "loc_add": 500,
        "loc_del": 200,
        "loc": 300,
    }
    rendered = render("dark", example)
    assert "<svg" in rendered
    assert "#0d1117" in rendered
    assert "Repositories" not in rendered
    assert "300" in rendered


if __name__ == "__main__":
    selfcheck()
    current_stats = fetch_stats()
    write_svgs(current_stats)
    print(f"Updated dark and light profile cards for @{USER}.")
