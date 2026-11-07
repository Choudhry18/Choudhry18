"""Render yearly profile boards from public GitHub commit activity."""

from collections import Counter
from datetime import datetime, timezone
from functools import cache
from html import escape
import json
from pathlib import Path
import subprocess
from urllib.request import urlopen
from xml.etree import ElementTree as ET

def query_user(fields):
    query = 'query { user(login: "Choudhry18") {' + fields + '} }'
    response = subprocess.check_output(["gh", "api", "graphql", "-f", f"query={query}"], text=True)
    return json.loads(response)["data"]["user"]


def yearly_activity():
    now = datetime.now(timezone.utc)
    years = query_user("contributionsCollection { contributionYears }")["contributionsCollection"]["contributionYears"]
    fields = []
    for year in sorted(years, reverse=True):
        end = now.strftime("%Y-%m-%dT%H:%M:%SZ") if year == now.year else f"{year}-12-31T23:59:59Z"
        fields.append(f"""
          y{year}: contributionsCollection(from: "{year}-01-01T00:00:00Z", to: "{end}") {{
            commitContributionsByRepository(maxRepositories: 100) {{
              repository {{ visibility primaryLanguage {{ name }} }}
              contributions {{ totalCount }}
            }}
          }}
        """)

    for alias, collection in query_user("".join(fields)).items():
        activity = Counter()
        for entry in collection["commitContributionsByRepository"]:
            repo = entry["repository"]
            language = repo["primaryLanguage"]
            if (
                repo["visibility"] == "PUBLIC"
                and language
                and language["name"] not in {"HTML", "CSS", "SCSS", "EJS", "Jupyter Notebook"}
            ):
                # The contribution records are grouped by repository and day.
                activity[language["name"]] += entry["contributions"]["totalCount"]
        if activity:
            yield int(alias[1:]), activity


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
      <rect x="1" y="1" width="36" height="36" rx="{[9, 14, 7, 12, 16][index]}"
        fill="url(#color{index})" stroke="#24292f" stroke-opacity=".25"/>
      <path d="M9 5h20" stroke="#fff" stroke-opacity=".65" stroke-linecap="round"/>
      {mark}
    </g>''')

    # Final arrangement. The center pair in rows one and two swap into this match.
    layout = (
        2, 1, 2, 0, 3, 1,
        1, 0, 0, 0, 2, 4,
        0, 2, 1, 2, 1, 0,
        3, 4, 0, 3, 4, 2,
        2, 0, 4, 2, 0, 3,
    )
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
        delay = 60 * column + 85 * (4 - row)
        movement = ""
        if len(languages) > 1:
            if index == 2:
                movement = ' class="swap-down"'
            elif index == 8:
                movement = ' class="swap-up"'
        tiles.append(f'''
    <g transform="translate({12 + 44 * column} {12 + 44 * row})">
      <g class="drop" style="animation-delay:{delay}ms">
        <g{movement}><use href="#piece{rank}"/></g>
      </g>
    </g>''')

    winner = escape(languages[0])
    names = escape(", ".join(languages))
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="360" height="304" viewBox="0 0 282 238" role="img" aria-labelledby="title description">
  <title id="title">Stack Match</title>
  <desc id="description">A six-column, five-row board with tiles for {names}. Three {winner} tiles match.</desc>
  <style>
    .surface {{ fill: #f6f8fa; stroke: #d1d9e0; }}
    .drop {{ animation: drop .62s cubic-bezier(.24,.78,.27,1) both; }}
    .swap-down {{ animation: swap-down .36s 1.28s ease-in-out both; }}
    .swap-up {{ animation: swap-up .36s 1.28s ease-in-out both; }}
    .match {{ animation: reveal .22s 1.66s both; }}
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
    @keyframes reveal {{ from {{ opacity: 0; }} }}
    @media (prefers-color-scheme: dark) {{
      .surface {{ fill: #151b23; stroke: #3d444d; }}
    }}
    @media (prefers-reduced-motion: reduce) {{
      .drop, .swap-down, .swap-up, .match {{ animation: none; }}
    }}
  </style>
  <defs>{''.join(definitions)}
    <clipPath id="board"><rect x="6" y="6" width="270" height="226" rx="6"/></clipPath>
  </defs>
  <rect class="surface" x=".5" y=".5" width="281" height="237" rx="10"/>
  <g clip-path="url(#board)">{''.join(tiles)}
    <rect class="match" x="55" y="55" width="128" height="40" rx="10"
      fill="none" stroke="#2da44e" stroke-width="2"/>
  </g>
</svg>
    '''.rstrip() + "\n"


def main():
    activity = Counter()
    for _, year_activity in yearly_activity():
        activity.update(year_activity)
    if not activity:
        raise SystemExit("No public language activity returned. Keeping the existing board.")

    languages = sorted(activity, key=lambda name: (-activity[name], name))[:5]
    root = Path(__file__).parent
    folder = root / "stack-match"
    folder.mkdir(exist_ok=True)
    (folder / "overview.svg").write_text(render_board(languages), encoding="utf-8")
    for existing in folder.glob("[0-9][0-9][0-9][0-9].svg"):
        existing.unlink()
    names = ", ".join(languages)
    readme = (
        "### Hey, I'm Abdullah\n\n"
        f"[![Play Stack Match and choose a year range. Tiles: {names}](stack-match/overview.svg)]"
        "(https://choudhry18.github.io/stack-match/)\n"
    )
    (root / "README.md").write_text(readme, encoding="utf-8")


if __name__ == "__main__":
    main()
