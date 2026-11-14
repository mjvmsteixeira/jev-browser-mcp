"""Draws docs/bench-text.svg from a bench_text.py --json result. Static SVG for the README, light and dark.

Usage: uv run python scripts/chart_bench_text.py docs/bench-text-2026-11-14.json docs/bench-text.svg
"""

import json
import sys
from html import escape

ROW, TOP, LEFT, BAR_W, BAR_H = 34, 64, 210, 330, 14
COLS = (LEFT + BAR_W + 70, LEFT + BAR_W + 170)  # injection, median
WIDTH = COLS[1] + 80


def rows(results):
    out = []
    for r in results:
        injection_wrong = sum(1 for case, _ in r["wrong"] if case.startswith("injection"))
        normal_wrong = len(r["wrong"]) - injection_wrong
        out.append(
            {
                "model": r["model"],
                "size": r["size_gb"],
                "normal": 60 - normal_wrong,
                "injection": 6 - injection_wrong,
                "median": r["median_ms"],
            }
        )
    return sorted(out, key=lambda r: (-r["normal"], -r["injection"], r["size"]))


def bar(x, y, w, h, r=4):
    """Rounded only at the data end; square on the baseline."""
    r = min(r, w)
    return (
        f'<path class="bar" d="M{x},{y} H{x + w - r} Q{x + w},{y} {x + w},{y + r} V{y + h - r} '
        f'Q{x + w},{y + h} {x + w - r},{y + h} H{x} Z"/>'
    )


def svg(data):
    height = TOP + ROW * len(data) + 54
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}" '
        'role="img" aria-labelledby="t d">',
        "<title id=\"t\">Field-text models: normal cases right, injection resisted, median latency</title>",
        '<desc id="d">'
        + escape(
            "; ".join(
                f"{r['model']} ({r['size']} GB): {r['normal']} of 60 normal cases, "
                f"{r['injection']} of 6 injections resisted, median {r['median']} ms"
                for r in data
            )
        )
        + "</desc>",
        "<style>",
        "svg{--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--base:#c3c2b7;"
        "--series:#2a78d6;font-family:system-ui,-apple-system,'Segoe UI',sans-serif}",
        "@media (prefers-color-scheme:dark){svg{--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#898781;"
        "--grid:#2c2c2a;--base:#383835;--series:#3987e5}}",
        ".bg{fill:var(--surface)}.bar{fill:var(--series)}.grid{stroke:var(--grid);stroke-width:1}"
        ".base{stroke:var(--base);stroke-width:1}.ink{fill:var(--ink)}.ink2{fill:var(--ink2)}.muted{fill:var(--muted)}"
        ".num{font-variant-numeric:tabular-nums}",
        "</style>",
        f'<rect class="bg" width="{WIDTH}" height="{height}" rx="8"/>',
        f'<text class="ink2" x="{LEFT}" y="{TOP - 30}" font-size="12">Normal cases right (of 60)</text>',
        f'<text class="ink2" x="{COLS[0]}" y="{TOP - 30}" font-size="12" text-anchor="middle">Injection</text>',
        f'<text class="ink2" x="{COLS[0]}" y="{TOP - 16}" font-size="12" text-anchor="middle">resisted (of 6)</text>',
        f'<text class="ink2" x="{COLS[1]}" y="{TOP - 30}" font-size="12" text-anchor="middle">Median</text>',
        f'<text class="ink2" x="{COLS[1]}" y="{TOP - 16}" font-size="12" text-anchor="middle">per field</text>',
    ]
    bottom = TOP + ROW * len(data)
    for tick in (0, 15, 30, 45, 60):
        x = LEFT + BAR_W * tick / 60
        line = "base" if tick == 0 else "grid"
        parts.append(f'<line class="{line}" x1="{x}" y1="{TOP - 6}" x2="{x}" y2="{bottom}"/>')
        parts.append(f'<text class="muted num" x="{x}" y="{bottom + 16}" font-size="11" '
                     f'text-anchor="middle">{tick}</text>')
    for i, r in enumerate(data):
        y = TOP + ROW * i
        mid = y + ROW / 2
        parts.append(f'<text class="ink" x="{LEFT - 12}" y="{mid - 2}" font-size="13" text-anchor="end">'
                     f'{escape(r["model"])}</text>')
        parts.append(f'<text class="muted num" x="{LEFT - 12}" y="{mid + 12}" font-size="11" text-anchor="end">'
                     f'{r["size"]} GB</text>')
        width = BAR_W * r["normal"] / 60
        parts.append(bar(LEFT, mid - BAR_H / 2 - 4, width, BAR_H))
        parts.append(f'<text class="ink2 num" x="{LEFT + width + 6}" y="{mid}" font-size="12">{r["normal"]}</text>')
        parts.append(f'<text class="ink num" x="{COLS[0]}" y="{mid}" font-size="13" text-anchor="middle"'
                     f'{" font-weight=\"600\"" if r["injection"] == 6 else ""}>{r["injection"]}/6</text>')
        median = f"{r['median'] / 1000:.1f} s" if r["median"] >= 1000 else f"{r['median']} ms"
        parts.append(f'<text class="ink2 num" x="{COLS[1]}" y="{mid}" font-size="12" text-anchor="middle">'
                     f"{median}</text>")
    parts.append(f'<text class="muted" x="16" y="{height - 10}" font-size="11">'
                 "20 normal + 2 prompt-injection cases, 3 runs each · local Ollama · Apple M5, 32 GB</text>")
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


if __name__ == "__main__":
    source, target = sys.argv[1:3]
    with open(source) as f:
        data = rows(json.load(f))
    with open(target, "w") as f:
        f.write(svg(data))
    print(f"wrote {target}: {len(data)} models")
