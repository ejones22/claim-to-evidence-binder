"""
Three figures for the report. All read from results already computed this
sprint (validity_check.json, compare_abstention.py / compare_second_model.py
outputs, datapipeline/results/sensitivity_strict_gold_test.json) -- no new
analysis, just plotting.

Run from dc_council/:
  python3 make_figures.py
Writes figure1_risk_coverage.png, figure2_abstention_by_model.png,
figure3_ranking_inversion.png.
"""
import json

import matplotlib.pyplot as plt

plt.rcParams.update({"font.size": 11, "figure.dpi": 150})


def figure1_risk_coverage():
    d = json.load(open("validity_check.json"))
    rc = d["risk_coverage"]
    thresholds = [r["threshold"] for r in rc]
    coverage = [r["coverage"] * 100 for r in rc]
    false_accept = [r["false_accept_rate"] * 100 for r in rc]

    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    ax.plot(thresholds, coverage, marker="o", label="Coverage (real matches accepted)", color="#2f7d4f")
    ax.plot(thresholds, false_accept, marker="o", label="False-accept rate (fabricated matches accepted)", color="#b4432f")
    ax.axvline(0.3, color="gray", linestyle="--", linewidth=1, label="Chosen threshold (0.3)")
    ax.set_xlabel("Word-overlap acceptance threshold")
    ax.set_ylabel("Percent")
    ax.set_title("Figure 1: Raising the threshold trades coverage for reliability", fontsize=12)
    ax.legend(fontsize=9, loc="lower center", bbox_to_anchor=(0.5, -0.48), ncol=1, frameon=True)
    ax.set_ylim(-3, 103)
    ax.grid(alpha=0.3)
    fig.savefig("figure1_risk_coverage.png", bbox_inches="tight")
    print("wrote figure1_risk_coverage.png")


def figure2_abstention_by_model():
    models = ["qwen2.5:3b\n(abstaining)", "qwen2.5:3b\n(forced)",
              "qwen2.5:7b\n(abstaining)", "qwen2.5:7b\n(forced)",
              "qwen3.5:9b\n(abstaining)", "qwen3.5:9b\n(forced)"]
    error_rates = [46.6, 47.5, 13.3, 41.5, 15.5, 33.0]
    coverages = [96.7, 100.0, 60.0, 100.0, 74.0, 100.0]
    colors = ["#2f7d4f", "#b4432f", "#2f7d4f", "#b4432f", "#2f7d4f", "#b4432f"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))

    ax1.bar(models, error_rates, color=colors)
    ax1.set_ylabel("Error rate on judged cases (%)")
    ax1.set_title("Error rate")
    ax1.tick_params(axis="x", labelsize=8)
    for i, v in enumerate(error_rates):
        ax1.text(i, v + 1, f"{v:.1f}%", ha="center", fontsize=9)

    ax2.bar(models, coverages, color=colors)
    ax2.set_ylabel("Coverage (%)")
    ax2.set_title("Coverage")
    ax2.tick_params(axis="x", labelsize=8)
    for i, v in enumerate(coverages):
        ax2.text(i, v + 1, f"{v:.1f}%", ha="center", fontsize=9)

    fig.suptitle("Figure 2: Abstention's benefit tracks model capability, not model size alone")
    fig.tight_layout()
    fig.savefig("figure2_abstention_by_model.png", bbox_inches="tight")
    print("wrote figure2_abstention_by_model.png")


def figure3_ranking_inversion():
    """
    The headline novelty finding: re-scoring every judge's already-collected
    held-out-test-split outputs (sensitivity_strict_gold_test.json) against
    the gold labels corrected for the independent-review-confirmed "supported"
    bias changes who's "best," not just by how much everyone's error rises.
    """
    d = json.load(open("../datapipeline/results/sensitivity_strict_gold_test.json"))
    # drop qwen2.5:3b: its ~50% error on a smaller, non-comparable n would
    # squash the scale for everyone else and it was never a contender
    rows = [r for r in d if "qwen2.5:3b" not in r["judge"]]
    name_map = {
        "adaption/qwen3.5-397b/abstain": "Adaption\nqwen3.5-397b",
        "anthropic/claude-haiku-5-5/abstain": "Claude\nHaiku 5.5",
        "anthropic/claude-sonnet-5-5/abstain": "Claude\nSonnet 5.5",
        "decision/d3:4b-q8_0/abstain": "d3:4b\n(decision)",
        "jev/jev-1.13.0/abstain": "Jev 1.13.0",
        "legacy/qwen2.5:7b/abstain": "qwen2.5:7b\n(local)",
        "legacy/qwen3.5:9b/abstain": "qwen3.5:9b\n(local)",
    }
    rows.sort(key=lambda r: r["orig_selective_error"])

    def spaced_positions(values, min_gap):
        """Nudge label y-positions apart just enough to avoid overlap,
        while keeping them as close as possible to their true values."""
        order = sorted(range(len(values)), key=lambda i: values[i])
        placed = [0.0] * len(values)
        prev = None
        for i in order:
            y = values[i]
            if prev is not None and y < prev + min_gap:
                y = prev + min_gap
            placed[i] = y
            prev = y
        return placed

    orig_vals = [r["orig_selective_error"] * 100 for r in rows]
    strict_vals = [r["strict_selective_error"] * 100 for r in rows]
    orig_label_y = spaced_positions(orig_vals, 1.7)
    strict_label_y = spaced_positions(strict_vals, 1.7)

    fig, ax = plt.subplots(figsize=(8.5, 6))
    highlight = "anthropic/claude-haiku-5-5/abstain"
    for i, r in enumerate(rows):
        j = r["judge"]
        color = "#2f7d4f" if j == highlight else "#9a9a9a"
        lw = 2.8 if j == highlight else 1.3
        ax.plot([0, 1], [orig_vals[i], strict_vals[i]],
                marker="o", color=color, linewidth=lw, zorder=3 if j == highlight else 2)
        ax.annotate(name_map.get(j, j), xy=(0, orig_vals[i]), xytext=(-0.06, orig_label_y[i]),
                    ha="right", va="center", fontsize=8.5,
                    arrowprops=dict(arrowstyle="-", color="#cccccc", lw=0.6) if abs(orig_label_y[i] - orig_vals[i]) > 0.3 else None)
        ax.annotate(name_map.get(j, j), xy=(1, strict_vals[i]), xytext=(1.06, strict_label_y[i]),
                    ha="left", va="center", fontsize=8.5,
                    fontweight="bold" if j == highlight else "normal",
                    arrowprops=dict(arrowstyle="-", color="#cccccc", lw=0.6) if abs(strict_label_y[i] - strict_vals[i]) > 0.3 else None)

    ax.set_xticks([0, 1])
    ax.set_xticklabels(["Original gold\n(ranked best → worst)", "Strict gold\n(sensitivity bound)"])
    ax.set_ylabel("Selective error on held-out test split (%)")
    ax.set_title("Figure 3: The \"best judge\" ranking inverts once the\nsupported-label bias is corrected for", fontsize=12)
    ax.set_xlim(-0.65, 1.65)
    ax.grid(alpha=0.2, axis="y")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    fig.savefig("figure3_ranking_inversion.png", bbox_inches="tight")
    print("wrote figure3_ranking_inversion.png")


if __name__ == "__main__":
    figure1_risk_coverage()
    figure2_abstention_by_model()
    figure3_ranking_inversion()
