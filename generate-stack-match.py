"""Render the profile board from the languages of public repos with commit activity."""

from collections import Counter
from html import escape
import json
from pathlib import Path
import subprocess
from urllib.request import urlopen
from xml.etree import ElementTree as ET

QUERY = """
query {
  user(login: "Choudhry18") {
    contributionsCollection {
      commitContributionsByRepository(maxRepositories: 100) {
        repository { visibility primaryLanguage { name } }
        contributions { totalCount }
      }
    }
  }
}
"""
# GitHub groups these records by repo and day. Count active repo-days by primary language.
contributions = json.loads(subprocess.check_output(
    ["gh", "api", "graphql", "-f", f"query={QUERY}"], text=True
))["data"]["user"]["contributionsCollection"]["commitContributionsByRepository"]
activity = Counter()
for entry in contributions:
    repo = entry["repository"]
    language = repo["primaryLanguage"]
    if (
        repo["visibility"] == "PUBLIC"
        and language
        and language["name"] not in {"HTML", "CSS", "SCSS", "Jupyter Notebook"}
    ):
        activity[language["name"]] += entry["contributions"]["totalCount"]

languages = sorted(activity, key=lambda name: (-activity[name], name))[:5]
if not languages:
    raise SystemExit("No public language activity returned. Keeping the existing board.")

icons = {
    "C": "c", "C++": "cplusplus", "C#": "csharp", "Go": "go", "Haskell": "haskell",
    "Java": "java", "JavaScript": "javascript", "Kotlin": "kotlin", "Python": "python",
    "Ruby": "ruby", "Rust": "rust", "Scala": "scala", "Swift": "swift",
    "TypeScript": "typescript", "Zig": "zig",
}
colors = {
    "Python": ("#e1f1ff", "#8fc6ed"), "Rust": ("#ffe4cc", "#f2a474"),
    "TypeScript": ("#d9e6ff", "#92aef0"), "JavaScript": ("#fff7c6", "#efd273"),
}
fallback_colors = [("#ddf8d8", "#98d5a6"), ("#f1e1ff", "#cdb2ed"), ("#fce2f0", "#e9a8ce")]
definitions = []
for index, language in enumerate(languages):
    top, bottom = colors.get(language, fallback_colors[index % len(fallback_colors)])
    logo = icons.get(language)
    if logo:
        # Devicon logos are embedded as vectors so GitHub can load the image without external resources.
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
        mark = ET.tostring(icon, encoding="unicode")
    else:
        mark = f'<text x="19" y="24" text-anchor="middle" fill="#24292f" font-size="11">{escape(language[:4])}</text>'
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
layout = (2, 1, 2, 0, 3, 1, 1, 0, 0, 0, 2, 4, 0, 2, 1, 2, 1, 0)
tiles = []
for index, rank in enumerate(layout):
    row, column = divmod(index, 6)
    if rank >= len(languages):
        if len(languages) == 3:
            rank = 1
        elif len(languages) == 2 and index == 2:
            rank = 1
        else:
            continue
    delay = 60 * column + 110 * (2 - row)
    movement = ""
    if len(languages) > 1:
        if index == 2:
            movement = ' class="swap-down"'
        elif index == 8:
            movement = ' class="swap-up"'
    tiles.append(f'''
    <g transform="translate({12 + 44 * column} {29 + 44 * row})">
      <g class="drop" style="animation-delay:{delay}ms">
        <g{movement}><use href="#piece{rank}"/></g>
      </g>
    </g>''')

winner = escape(languages[0])
names = escape(", ".join(languages))
svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="282" height="168" viewBox="0 0 282 168" role="img" aria-labelledby="title description">
  <title id="title">Stack Match</title>
  <desc id="description">Tiles for {names} fall into place and three {winner} tiles match.</desc>
  <style>
    svg {{ font-family: ui-monospace, monospace; }}
    .surface {{ fill: #f6f8fa; stroke: #d1d9e0; }}
    .label {{ fill: #57606a; }}
    .result {{ fill: #116329; animation: reveal 1.75s both; }}
    .drop {{ animation: drop .62s cubic-bezier(.24,.78,.27,1) both; }}
    .swap-down {{ animation: swap-down .36s 1.16s ease-in-out both; }}
    .swap-up {{ animation: swap-up .36s 1.16s ease-in-out both; }}
    .match {{ animation: reveal 1.75s both; }}
    @keyframes drop {{
      0% {{ transform: translateY(-140px); opacity: 0; }}
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
    @keyframes reveal {{ 0%, 87% {{ opacity: 0; }} 100% {{ opacity: 1; }} }}
    @media (prefers-color-scheme: dark) {{
      .surface {{ fill: #151b23; stroke: #3d444d; }}
      .label {{ fill: #9198a1; }}
      .result {{ fill: #7ee787; }}
    }}
    @media (prefers-reduced-motion: reduce) {{
      .drop, .swap-down, .swap-up, .result, .match {{ animation: none; }}
    }}
  </style>
  <defs>{''.join(definitions)}
    <clipPath id="board"><rect x="6" y="24" width="270" height="138" rx="6"/></clipPath>
  </defs>
  <rect class="surface" x=".5" y=".5" width="281" height="167" rx="10"/>
  <text class="label" x="13" y="18" font-size="10" letter-spacing="1.3">STACK MATCH</text>
  <text class="result" x="269" y="18" font-size="10" text-anchor="end">{winner} ×3</text>
  <g clip-path="url(#board)">{''.join(tiles)}
    <rect class="match" x="55" y="72" width="128" height="40" rx="10"
      fill="none" stroke="#2da44e" stroke-width="2"/>
  </g>
</svg>
'''
Path(__file__).with_name("stack-match.svg").write_text(svg, encoding="utf-8")
