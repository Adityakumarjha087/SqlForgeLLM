"""Milestone 5: compare eval runs by SQL feature and difficulty; save charts.

Usage:
  uv run python scripts/analyze_errors.py base=outputs/eval/base-full.json \\
      sft=outputs/eval/sft-full.json grpo=outputs/eval/grpo-full.json

Any number of name=path pairs works. Writes docs/assets/overall_accuracy.png and
docs/assets/accuracy_by_category.png, and appends the comparison table to
docs/results.md.
"""

import datetime
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sqlforge.analysis import FEATURES, accuracy_by_category

REPO_ROOT = Path(__file__).resolve().parents[1]
ASSETS = REPO_ROOT / "docs" / "assets"
# Categorical slots 1-3 (validated: CVD-safe, fixed order; aqua's low surface
# contrast is relieved by the value labels drawn on every bar).
SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
INK, MUTED = "#333230", "#8a887d"


def style_axes(ax):
    for side in ["top", "right"]:
        ax.spines[side].set_visible(False)
    for side in ["left", "bottom"]:
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=INK, labelsize=9)
    ax.yaxis.grid(True, color="#e5e4df", linewidth=0.75)
    ax.set_axisbelow(True)


def label_bars(ax, bars):
    for bar in bars:
        ax.annotate(
            f"{bar.get_height():.0%}",
            (bar.get_x() + bar.get_width() / 2, bar.get_height()),
            ha="center",
            va="bottom",
            fontsize=8,
            color=INK,
        )


def main() -> None:
    runs: dict[str, dict] = {}
    for arg in sys.argv[1:]:
        name, _, path = arg.partition("=")
        predictions = json.loads(Path(path).read_text())["predictions"]
        runs[name] = accuracy_by_category(predictions)
    if not runs:
        sys.exit(__doc__)
    ASSETS.mkdir(parents=True, exist_ok=True)

    names = list(runs)
    colors = SERIES_COLORS[: len(names)]

    # Chart 1: overall execution accuracy per run.
    fig, ax = plt.subplots(figsize=(5, 3.5), facecolor="white")
    values = [runs[n]["overall"]["accuracy"] for n in names]
    bars = ax.bar(names, values, color=colors, width=0.55)
    label_bars(ax, bars)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("execution accuracy", fontsize=9, color=INK)
    ax.set_title("Spider dev: execution accuracy", fontsize=11, color=INK)
    style_axes(ax)
    fig.savefig(ASSETS / "overall_accuracy.png", dpi=150, bbox_inches="tight")

    # Chart 2: per-category grouped bars.
    categories = FEATURES + [f"difficulty/{d}" for d in ["easy", "medium", "hard", "extra"]]
    categories = [c for c in categories if any(runs[n][c]["n"] for n in names)]
    x = range(len(categories))
    width = 0.8 / len(names)
    fig, ax = plt.subplots(figsize=(max(7, len(categories) * 1.1), 4), facecolor="white")
    for i, name in enumerate(names):
        vals = [runs[name][c]["accuracy"] for c in categories]
        offset = [xi + i * width - 0.4 + width / 2 for xi in x]
        bars = ax.bar(offset, vals, width=width * 0.92, color=colors[i], label=name)
        if len(names) <= 2:
            label_bars(ax, bars)
    counts = [runs[names[0]][c]["n"] for c in categories]
    ax.set_xticks(list(x))
    ax.set_xticklabels(
        [f"{c.split('/')[-1]}\n(n={n})" for c, n in zip(categories, counts, strict=True)],
        fontsize=8,
    )
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("execution accuracy", fontsize=9, color=INK)
    ax.set_title("Execution accuracy by SQL feature and difficulty", fontsize=11, color=INK)
    ax.legend(frameon=False, fontsize=9)
    style_axes(ax)
    fig.savefig(ASSETS / "accuracy_by_category.png", dpi=150, bbox_inches="tight")

    # Markdown table appended to results.
    lines = [
        "",
        f"## {datetime.date.today()} — Error analysis ({', '.join(names)})",
        "",
        "| Category | n | " + " | ".join(names) + " |",
        "|---|---|" + "---|" * len(names),
    ]
    for c in ["overall", *categories]:
        row = [f"{runs[n][c]['accuracy']:.1%}" for n in names]
        lines.append(f"| {c} | {runs[names[0]][c]['n']} | " + " | ".join(row) + " |")
    lines += [
        "",
        "![overall](assets/overall_accuracy.png)",
        "![by category](assets/accuracy_by_category.png)",
        "",
    ]
    results = REPO_ROOT / "docs" / "results.md"
    results.write_text(results.read_text() + "\n".join(lines))
    print("\n".join(lines))
    print(f"\nCharts saved to {ASSETS}")


if __name__ == "__main__":
    main()
