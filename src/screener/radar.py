"""
src/screener/radar.py

Sprint 3, Day 19 — Radar Charts.

Generates an 8-axis polar/radar chart per company: ROE, ROCE, NPM, D/E,
FCF score, PAT CAGR 5yr, Revenue CAGR 5yr, Composite Score — each axis
normalised to a 0-100 "score" (via the same P10/P90 winsorization used
for the composite score, so a company's raw FCF in Crore doesn't dwarf
its ROE percentage on the same plot) — with the company's own polygon
filled and its peer group's average overlaid as a dashed outline.

Companies with no peer group get a standalone two-bar chart (their
composite score vs. the full Nifty 100 universe average) instead of a
radar, per spec Day 19's "single-metric standalone chart... with Nifty
100 average as reference".

Output: reports/radar_charts/<ticker>_radar.png
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless — no display backend available/needed
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.screener.composite import _winsorize_scale, compute_composite_scores

RADAR_AXES = [
    ("return_on_equity_pct", "ROE", True),
    ("return_on_capital_employed_pct", "ROCE", True),
    ("net_profit_margin_pct", "NPM", True),
    ("debt_to_equity", "D/E", False),  # inverted: lower D/E -> higher score
    ("free_cash_flow_cr", "FCF", True),
    ("pat_cagr_5yr", "PAT CAGR 5yr", True),
    ("revenue_cagr_5yr", "Revenue CAGR 5yr", True),
    ("composite_score", "Composite Score", True),  # already 0-100
]


def _build_radar_scores(universe: pd.DataFrame) -> pd.DataFrame:
    """Adds one *_score column (0-100) per radar axis to `universe`."""
    universe = universe.copy()
    for col, _label, higher_is_better in RADAR_AXES:
        if col == "composite_score":
            universe["composite_score_score"] = universe["composite_score"]
            continue
        universe[f"{col}_score"] = _winsorize_scale(
            universe[col], low_pct=10, high_pct=90, higher_is_better=higher_is_better
        )
    return universe


def _plot_radar(
    ax, company_values: list, peer_avg_values: list, labels: list, title: str, subtitle: str
):
    n = len(labels)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    angles += angles[:1]

    company_plot = company_values + company_values[:1]
    peer_plot = peer_avg_values + peer_avg_values[:1]

    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylim(0, 100)
    ax.set_yticks([25, 50, 75, 100])
    ax.set_yticklabels(["25", "50", "75", "100"], fontsize=8, color="gray")

    ax.plot(angles, company_plot, color="#1F4E78", linewidth=2, label=title)
    ax.fill(angles, company_plot, color="#1F4E78", alpha=0.25)

    ax.plot(angles, peer_plot, color="#C00000", linewidth=1.5, linestyle="--", label=subtitle)

    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=9)


def generate_radar_chart(
    company_id: str, universe_with_scores: pd.DataFrame, output_dir: Path
) -> Path:
    row = universe_with_scores[universe_with_scores["company_id"] == company_id]
    if row.empty:
        raise ValueError(f"{company_id} not found in screener universe")
    row = row.iloc[0]

    peer_group = row.get("peer_group_name")
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{company_id}_radar.png"

    labels = [label for _col, label, _h in RADAR_AXES]
    company_values = [
        row[f"{col}_score"] if col != "composite_score" else row["composite_score"]
        for col, _label, _h in RADAR_AXES
    ]
    company_values = [0.0 if pd.isna(v) else float(v) for v in company_values]

    if pd.isna(peer_group) or peer_group is None:
        # No peer group -> standalone two-bar chart vs Nifty 100 average.
        universe_avg = universe_with_scores["composite_score"].mean()
        fig, ax = plt.subplots(figsize=(5, 4))
        bars = ax.bar(
            [row["company_name"] or company_id, "Nifty 100 Average"],
            [row["composite_score"], universe_avg],
            color=["#1F4E78", "#BFBFBF"],
        )
        ax.set_ylabel("Composite Score (0-100)")
        ax.set_title(
            f"{company_id} — No Peer Group Assigned\nComposite Score vs. Nifty 100 Average"
        )
        ax.bar_label(bars, fmt="%.1f")
        ax.set_ylim(0, 100)
        plt.tight_layout()
        fig.savefig(out_path, dpi=120)
        plt.close(fig)
        return out_path

    peer_members = universe_with_scores[universe_with_scores["peer_group_name"] == peer_group]
    peer_avg_values = []
    for col, _label, _h in RADAR_AXES:
        score_col = "composite_score" if col == "composite_score" else f"{col}_score"
        peer_avg_values.append(float(peer_members[score_col].mean()))

    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw={"polar": True})
    _plot_radar(
        ax,
        company_values,
        peer_avg_values,
        labels,
        title=f"{row['company_name'] or company_id}",
        subtitle=f"{peer_group} Average",
    )
    ax.set_title(f"{company_id} vs. {peer_group} Peer Group", fontsize=12, pad=30)
    plt.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path


def generate_all_radar_charts(
    conn: sqlite3.Connection,
    universe: pd.DataFrame,
    financial_ratios: pd.DataFrame,
    output_dir: Path,
) -> list:
    scored = compute_composite_scores(universe, financial_ratios)
    scored = _build_radar_scores(scored)

    paths = []
    for company_id in scored["company_id"]:
        path = generate_radar_chart(company_id, scored, output_dir)
        paths.append(path)
    return paths
