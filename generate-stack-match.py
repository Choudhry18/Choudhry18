"""Render the profile board from combined public and private commit totals."""

from collections import Counter
from datetime import datetime, timezone
from functools import cache
from html import escape
import json
from pathlib import Path
import subprocess
from urllib.request import urlopen
from xml.etree import ElementTree as ET

EXCLUDED_LANGUAGES = {"HTML", "CSS", "SCSS", "EJS", "Jupyter Notebook"}


def github_json(*arguments, payload=None):
    response = subprocess.run(
        ["gh", "api", *arguments],
        input=json.dumps(payload) if payload is not None else None,
        capture_output=True,
        text=True,
    )
    if response.returncode:
        raise SystemExit("GitHub could not return contribution data. Keeping the existing board.")
    return json.loads(response.stdout)


def graphql(query, **variables):
    return github_json("graphql", "--input", "-", payload={"query": query, "variables": variables})["data"]


def query_user(fields):
    return graphql('query { user(login: "Choudhry18") {' + fields + '} }')["user"]


def private_activity(windows):
    # The contribution collection can hide private rows even when repo history is accessible.
    viewer = graphql("query { viewer { id login } }")["viewer"]
    if viewer["login"].casefold() != "choudhry18":
        raise SystemExit("Use Abdullah's GitHub sign-in to refresh private contribution totals.")
    pages = github_json(
        "--paginate", "--slurp",
        "user/repos?visibility=private&affiliation=owner%2Ccollaborator%2Corganization_member&per_page=100",
    )
    ids = [
        repo["node_id"] for page in pages for repo in page
        if repo["visibility"] == "private" and not repo["fork"]
    ]
    history = "\n".join(
        f'y{year}: history(author: {{id: $author}}, since: "{start}", until: "{end}") {{ totalCount }}'
        for year, (start, end) in windows.items()
    )
    query = f"""
      query($ids: [ID!]!, $author: ID!) {{
        nodes(ids: $ids) {{
          ... on Repository {{
            visibility
            primaryLanguage {{ name }}
            defaultBranchRef {{ target {{ ... on Commit {{ {history} }} }} }}
          }}
        }}
      }}
    """
    by_year = {year: Counter() for year in windows}
    for offset in range(0, len(ids), 20):
        repos = graphql(query, ids=ids[offset:offset + 20], author=viewer["id"])["nodes"]
        for repo in repos:
            if repo is None:
                raise SystemExit("A private repository became unavailable. Keeping the existing board.")
            language = (repo["primaryLanguage"] or {}).get("name")
            branch = repo["defaultBranchRef"]
            if repo["visibility"] != "PRIVATE" or not branch or not language or language in EXCLUDED_LANGUAGES:
                continue
            for year in windows:
                count = branch["target"][f"y{year}"]["totalCount"]
                if count:
                    by_year[year][language] += count
    if not any(by_year.values()):
        raise SystemExit("No private commit totals were available. Keeping the existing board.")
    return by_year


def yearly_activity():
    now = datetime.now(timezone.utc)
    years = query_user("contributionsCollection { contributionYears }")["contributionsCollection"]["contributionYears"]
    windows = {
        year: (
            f"{year}-01-01T00:00:00Z",
            now.strftime("%Y-%m-%dT%H:%M:%SZ") if year == now.year else f"{year}-12-31T23:59:59Z",
        )
        for year in sorted({*years, now.year}, reverse=True)
    }
    fields = []
    for year, (start, end) in windows.items():
        fields.append(f"""
          y{year}: contributionsCollection(from: "{start}", to: "{end}") {{
            commitContributionsByRepository(maxRepositories: 100) {{
              repository {{ visibility primaryLanguage {{ name }} }}
              contributions {{ totalCount }}
            }}
          }}
        """)

    by_year = private_activity(windows)
    for alias, collection in query_user("".join(fields)).items():
        year = int(alias[1:])
        for entry in collection["commitContributionsByRepository"]:
            repo = entry["repository"]
            language = (repo["primaryLanguage"] or {}).get("name")
            if repo["visibility"] == "PUBLIC" and language and language not in EXCLUDED_LANGUAGES:
                by_year[year][language] += entry["contributions"]["totalCount"]
        if by_year[year]:
            yield year, by_year[year]


icons = {
    "C": "c", "C++": "cplusplus", "C#": "csharp", "Go": "go", "Haskell": "haskell",
    "Java": "java", "JavaScript": "javascript", "Kotlin": "kotlin", "Python": "python",
    "Ruby": "ruby", "Rust": "rust", "Scala": "scala", "Swift": "swift",
    "TypeScript": "typescript", "Zig": "zig",
}
colors = {
    "Python": ("#e1f1ff", "#8fc6ed"), "Rust": ("#ffe4cc", "#f2a474"),
    "TypeScript": ("#d9e6ff", "#92aef0"), "JavaScript": ("#fff7c6", "#efd273"),
    "Java": ("#fce1cd", "#eaba96"), "Haskell": ("#ede0fb", "#bea4d8"),
    "C": ("#d6f2ed", "#94cbbd"), "C++": ("#e8d9ff", "#b6a0e6"),
    "Scala": ("#ffdbe6", "#f1a0b6"),
}
fallback_colors = [("#ddf8d8", "#98d5a6"), ("#f1e1ff", "#cdb2ed"), ("#fce2f0", "#e9a8ce")]
@cache
def tile_logo(logo):
    if not logo:
        return '<path d="m19 9 10 10-10 10L9 19Z" fill="none" stroke="#24292f" stroke-width="2"/>'
    # Embed Devicon vectors so the board needs no external resources when loaded.
    version = "6910f0503efdd315c8f9b858234310c06e04d9c0"
    url = f"https://cdn.jsdelivr.net/gh/devicons/devicon@{version}/icons/{logo}/{logo}-original.svg"
    with urlopen(url, timeout=10) as response:
        icon = ET.fromstring(response.read())
    for node in icon.iter():
        for attribute, value in node.attrib.items():
            if attribute == "id":
                node.set(attribute, f"{logo}-{value}")
            elif value.startswith("url(#"):
                node.set(attribute, value.replace("url(#", f"url(#{logo}-", 1))
            elif attribute.endswith("href") and value.startswith("#"):
                node.set(attribute, f"#{logo}-{value[1:]}")
    icon.attrib.update({"x": "7", "y": "7", "width": "24", "height": "24"})
    return ET.tostring(icon, encoding="unicode")


def render_board(languages):
    definitions = []
    for index, language in enumerate(languages):
        top, bottom = colors.get(language, fallback_colors[index % len(fallback_colors)])
        mark = tile_logo(icons.get(language))
        definitions.append(f'''
    <linearGradient id="color{index}" x2="0%" y2="100%">
      <stop stop-color="{top}"/><stop offset="1" stop-color="{bottom}"/>
    </linearGradient>
    <g id="piece{index}">
      <rect x="1" y="1" width="36" height="36" rx="{[9, 14, 7, 12, 16, 18][index]}"
        fill="url(#color{index})" stroke="#24292f" stroke-opacity=".25"/>
      <path d="M9 5h20" stroke="#fff" stroke-opacity=".65" stroke-linecap="round"/>
      {mark}
    </g>''')

    # Arrange the board immediately after the swap, before the match clears.
    layout = (
        2, 5, 2, 0, 3, 5,
        1, 0, 0, 0, 2, 4,
        0, 2, 1, 2, 5, 0,
        3, 4, 0, 3, 4, 2,
        2, 0, 4, 2, 0, 3,
    )
    after_match = {1: "settle", 2: "settle", 3: "settle", 7: "clear", 8: "clear", 9: "clear"}
    tiles = []
    for index, rank in enumerate(layout):
        row, column = divmod(index, 6)
        if rank >= len(languages):
            if len(languages) >= 3:
                rank = 1
            elif len(languages) == 2 and index == 2:
                rank = 1
            else:
                continue
        delay = 280 + 60 * column + 85 * (4 - row)
        movement = ""
        if len(languages) > 1:
            if index == 2:
                movement = ' class="swap-down"'
            elif index == 8:
                movement = ' class="swap-up"'
        tiles.append(f'''
    <g transform="translate({12 + 44 * column} {12 + 44 * row})">
      <g class="drop" style="animation-delay:{delay}ms">
        <g{movement}><use class="{after_match.get(index, "")}" href="#piece{rank}"/></g>
      </g>
    </g>''')

    winner = escape(languages[0])
    names = escape(", ".join(languages))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="360" height="304" viewBox="0 0 282 238" role="img" aria-labelledby="title description">
  <title id="title">Stack Match</title>
  <desc id="description">Tiles for {names} drop into an empty board. Three {winner} tiles match and disappear, and the tiles above fall.</desc>
  <style>
    .surface {{ fill: #f6f8fa; stroke: #d1d9e0; }}
    .slot {{ fill: #e9edf2; }}
    .drop {{ animation: drop .62s cubic-bezier(.24,.78,.27,1) both; }}
    .swap-down {{ animation: swap-down .36s 1.61s ease-in-out both; }}
    .swap-up {{ animation: swap-up .36s 1.61s ease-in-out both; }}
    .match {{ animation: highlight .66s 1.98s both; }}
    .clear {{
      transform-box: fill-box;
      transform-origin: center;
      animation: clear .34s 2.34s ease-in-out both;
    }}
    .settle {{ animation: settle .4s 2.68s cubic-bezier(.42,0,.8,1) both; }}
    @keyframes drop {{
      0% {{ transform: translateY(-228px); opacity: 0; }}
      15% {{ opacity: 1; }}
      82% {{ transform: translateY(3px); }}
      100% {{ transform: translateY(0); }}
    }}
    @keyframes swap-down {{
      0% {{ transform: translateY(44px); }}
      50% {{ transform: translate(-12px, 22px); }}
    }}
    @keyframes swap-up {{
      0% {{ transform: translateY(-44px); }}
      50% {{ transform: translate(12px, -22px); }}
    }}
    @keyframes highlight {{
      0%, 100% {{ opacity: 0; }}
      16%, 60% {{ opacity: 1; }}
    }}
    @keyframes clear {{
      25% {{ transform: scale(1.1); opacity: 1; }}
      100% {{ transform: scale(.2); opacity: 0; }}
    }}
    @keyframes settle {{
      75% {{ transform: translateY(46px); }}
      100% {{ transform: translateY(44px); }}
    }}
    @media (prefers-color-scheme: dark) {{
      .surface {{ fill: #151b23; stroke: #3d444d; }}
      .slot {{ fill: #212933; }}
    }}
    @media (prefers-reduced-motion: reduce) {{
      .drop, .swap-down, .swap-up, .match, .clear, .settle {{ animation: none; }}
      .match, .clear {{ opacity: 0; }}
      .settle {{ transform: translateY(44px); }}
    }}
  </style>
  <defs>{''.join(definitions)}
    <pattern id="slots" x="12" y="12" width="44" height="44" patternUnits="userSpaceOnUse">
      <rect class="slot" x="1" y="1" width="36" height="36" rx="8"/>
    </pattern>
    <clipPath id="board"><rect x="6" y="6" width="270" height="226" rx="6"/></clipPath>
  </defs>
  <rect class="surface" x=".5" y=".5" width="281" height="237" rx="10"/>
  <g clip-path="url(#board)">
    <rect x="12" y="12" width="264" height="220" fill="url(#slots)"/>{''.join(tiles)}
    <rect class="match" x="55" y="55" width="128" height="40" rx="10"
      fill="none" stroke="#2da44e" stroke-width="2.5"/>
  </g>
</svg>
    '''.rstrip() + "\n"


def main():
    activity = Counter()
    years = dict(yearly_activity())
    for year_activity in years.values():
        activity.update(year_activity)
    if not activity:
        raise SystemExit("No language activity returned. Keeping the existing board.")

    languages = sorted(activity, key=lambda name: (-activity[name], name))[:5]
    if "Rust" in activity and "Rust" not in languages:
        languages.append("Rust")
    root = Path(__file__).parent
    folder = root / "stack-match"
    folder.mkdir(exist_ok=True)
    (folder / "overview.svg").write_text(render_board(languages), encoding="utf-8")
    for existing in folder.glob("[0-9][0-9][0-9][0-9].svg"):
        existing.unlink()
    names = ", ".join(languages)
    readme = (
        f"[![Watch a match clear, then click to play Stack Match. Tiles: {names}](stack-match/overview.svg?v=combined)]"
        "(https://choudhry18.github.io/stack-match/)\n"
    )
    (root / "README.md").write_text(readme, encoding="utf-8")
    return years


if __name__ == "__main__":
    main()
