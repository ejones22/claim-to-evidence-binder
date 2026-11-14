"""
Two figures for the report. Both read from results already computed this
sprint (validity_check.json, compare_abstention.py / compare_second_model.py
outputs) -- no new analysis, just plotting.

Run from dc-council/dc_etl/:
  python3 make_figures.py
Writes figure1_risk_coverage.png, figure2_abstention_by_model.png.
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


if __name__ == "__main__":
    figure1_risk_coverage()
    figure2_abstention_by_model()
