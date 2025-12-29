# engine/display_results.py

import json
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import matplotlib.ticker as ticker
import pandas as pd
import csv
import os
import numpy as np
from collections import defaultdict


def _apply_matplotlib_style() -> None:
    """Apply lightweight, professional matplotlib styling defaults.

    Goal: sharper text/lines in saved images and cleaner aesthetics.
    Safe to call multiple times.
    """

    # Higher DPI makes saved PNGs crisper (and improves text rendering).
    # We set both figure + savefig defaults; individual savefig() can override.
    plt.rcParams.update(
        {
            "figure.dpi": 200,
            "savefig.dpi": 350,
            "savefig.bbox": "tight",
            "savefig.facecolor": "white",
            "figure.facecolor": "white",
            "axes.facecolor": "#FCFCFC",
            "axes.edgecolor": "#2B2B2B",
            "axes.linewidth": 0.9,
            "axes.grid": True,
            "grid.alpha": 0.25,
            "grid.linewidth": 0.8,
            "grid.color": "#2B2B2B",
            "font.family": "DejaVu Sans",
            "font.size": 11.5,
            "axes.titlesize": 15,
            "axes.labelsize": 12.5,
            "xtick.labelsize": 10.5,
            "ytick.labelsize": 10.5,
            "legend.fontsize": 10.5,
            "legend.frameon": True,
            "legend.framealpha": 0.90,
            "legend.borderpad": 0.5,
            "lines.linewidth": 1.0,
            "lines.solid_capstyle": "round",
            "lines.antialiased": True,
            "patch.antialiased": True,
            "text.antialiased": True,
        }
    )

def _format_event_brackets(labels: list[str]) -> str:
    """Format event labels as: [Event1] [Event2] ..."""
    out: list[str] = []
    for lbl in labels:
        if lbl is None:
            continue
        s = str(lbl).strip()
        if not s:
            continue
        out.append(f"[{s}]")
    return " ".join(out)

def print_simulation(simulations, granularity='monthly'):
    for scenario, results in simulations.items():
        print(f"\n--- {scenario.upper()} RETURN SCENARIO ---")
        print(f"{'Age':<8}{'Month':<6}{'Year':<8}{'Portfolio':>17}{'Income':>12}"
              f"{'Taxed Income':>16}{'Monthly Raw Exp.':>20}{'Disc. Exp.':>15}"
              f"{'Montly Net Exp.':>15}{'Montly Gross Up':>15}     {'Event'}")
        for year_data in results:
            if granularity == 'yearly' and year_data['month'] != 1:
                continue
            print(f"{year_data['age']:>6.2f}  {year_data['month']:<6}{year_data['year']:<8}"
                  f"${year_data['portfolio_end']:>15,.2f}"
                  f"${year_data['monthly_income']:>11,.2f}"
                  f"${year_data['monthly_taxed_income']:>15,.2f}"
                  f"${year_data['monthly_raw_expenses']:>19,.2f}"
                  f"${year_data.get('monthly_discretionary_expenses', 0):>14,.2f}"
                  f"${year_data['monthly_net_expenses']:>14,.2f}"
                  f"${year_data['monthly_gross_up']:>14,.2f}     "
                  f"{year_data['event']}")

def print_simulation_csv(simulations, filename_prefix="simulation_output", granularity='monthly'):
    for scenario, results in simulations.items():
        filtered = [r for r in results if granularity != 'yearly' or r['month'] == 1]
        for r in filtered:
            r["age"] = round(r["age"], 2)
        df = pd.DataFrame(filtered)
        output_file = f"{filename_prefix}_{scenario}.csv"
        df.to_csv(output_file, index=False)
        print(f"Saved CSV output to {output_file}")

def graph_simulation_with_montecarlo(simulations, ages, mc_percentiles, user_name="User", description="Simulation",
                                     save_path="out/simulation.png", mc_sample_run=None, event_labels=None):
    _apply_matplotlib_style()
    fig, ax1 = plt.subplots(figsize=(12, 6), constrained_layout=True)

    # Professional baseline tweaks (spines + tick density)
    ax1.spines['top'].set_visible(False)
    ax1.spines['right'].set_visible(False)
    ax1.set_axisbelow(True)
    ax1.minorticks_on()
    ax1.grid(True, which="major")
    ax1.grid(True, which="minor", alpha=0.10)
    # Used later for the Austerity Index overlay; initialize up-front so we
    # never reference it before assignment (e.g., after refactors).
    austerity_results = None

    # Simulation lines (portfolio)
    for label, results in simulations.items():
        age_vals = [entry["age"] for entry in results]
        values = [entry["portfolio_end"] / 1_000_000 for entry in results]
        ax1.plot(age_vals, values, label=f"{label.capitalize()} Return")

    # Monte Carlo envelope and median
    median = np.array(mc_percentiles[1]) / 1_000_000
    p10 = np.array(mc_percentiles[0]) / 1_000_000
    p90 = np.array(mc_percentiles[2]) / 1_000_000

    ax1.plot(ages, median, label="Monte Carlo Median", linestyle='--')
    ax1.fill_between(
        ages,
        p10,
        p90,
        color="#6C6C6C",
        alpha=0.22,
        label="10th-90th Percentile Range",
    )

    # Optional: a sample Monte Carlo run
    if mc_sample_run:
        sample_ages = [point["age"] for point in mc_sample_run]
        sample_vals = [point.get("portfolio", point.get("portfolio_value", 0)) / 1_000_000 for point in mc_sample_run]
        ax1.plot(sample_ages, sample_vals, linestyle=':', linewidth=1.5, label="Sample MC Run")

    # --- Austerity Index (%), banded into the middle third of the chart ---
    # We map:
    #   33% height of plot -> 0%
    #   66% height of plot -> 100%
    #
    # Implementation:
    #   - Compute austerity% from requested vs actual discretionary
    #   - Convert austerity% into primary-axis Y units in the middle band
    #   - Add a right-side secondary axis with an inverse transform (0–100%)
    austerity_results = None
    if isinstance(simulations, dict):
        austerity_results = simulations.get("expected") or next(iter(simulations.values()), None)

    if austerity_results:
        # Ensure y-limits are established from the portfolio data first
        y_min, y_max = ax1.get_ylim()
        y_rng = (y_max - y_min) if (y_max - y_min) != 0 else 1.0

        band_lo = y_min + (1.0 / 3.0) * y_rng
        band_hi = y_min + (2.0 / 3.0) * y_rng
        band_rng = band_hi - band_lo  # == y_rng/3

        # Subtle background shading to indicate the "austerity band"
        # Very low opacity so it reads as structure, not data
        ax1.axhspan(
            band_lo,
            band_hi,
            color="#1E88E5",   # match austerity line (azure)
            alpha=0.04,
            zorder=0,
        )

        austerity_age = [entry["age"] for entry in austerity_results]
        austerity_pct = []
        for entry in austerity_results:
            req = float(entry.get("monthly_requested_discretionary_expenses", 0.0) or 0.0)
            actual = float(entry.get("monthly_discretionary_expenses", 0.0) or 0.0)
            if req <= 0.0:
                austerity_pct.append(0.0)
            else:
                cut = (1.0 - (actual / req)) * 100.0
                austerity_pct.append(max(0.0, min(100.0, cut)))

        # Transform austerity% -> primary-axis Y in middle band
        austerity_y = [band_lo + (p / 100.0) * band_rng for p in austerity_pct]

        # Subtle but visible color + style
        austerity_color = "#1E88E5"  # azure-ish blue, subtle but readable
        ax1.plot(
            austerity_age,
            austerity_y,
            label="Austerity Index",
            linestyle="-",
            linewidth=1.8,
            alpha=0.85,
            color=austerity_color,
        )

        # Under-the-graph shading (within the austerity band):
        # More austerity => more filled area from 0% (band_lo) up to current level.
        ax1.fill_between(
            austerity_age,
            [band_lo] * len(austerity_y),
            austerity_y,
            alpha=0.10,      # low opacity so it doesn't overwhelm
            color=austerity_color,
            linewidth=0,
            zorder=1,
        )

        def _aust_to_y(pct):
            """Map austerity percent (0..100) -> primary-axis y in the middle band.
            Must accept scalars OR numpy arrays (matplotlib may pass arrays).
            """
            p = np.asarray(pct, dtype=float)
            p = np.clip(p, 0.0, 100.0)
            return band_lo + (p / 100.0) * band_rng

        def _y_to_aust(y):
            """Inverse: primary-axis y -> austerity percent (0..100).
            Must accept scalars OR numpy arrays (matplotlib may pass arrays).
            """
            yy = np.asarray(y, dtype=float)
            if band_rng == 0:
                return np.zeros_like(yy, dtype=float)
            return ((yy - band_lo) / band_rng) * 100.0

        # IMPORTANT:
        # secondary_yaxis() spans the full height visually, which makes the right axis
        # look like 0% is at the bottom and 100% at the top. We instead use a twin axis
        # and place ticks ONLY in the middle band (33%..66% of plot height).
        ax2 = ax1.twinx()
        ax2.set_ylim(ax1.get_ylim())  # primary units
        ax2.grid(False, which="both")

        # twinx() shares the x-axis; ax2 should never contribute x ticks/locators
        ax2.xaxis.set_visible(False)

        tick_pcts = [0, 25, 50, 75, 100]
        tick_ys = [_aust_to_y(p) for p in tick_pcts]  # primary-y positions in the band

        ax2.set_yticks(tick_ys)
        ax2.set_yticklabels([f"{p}%" for p in tick_pcts])
        ax2.set_ylabel("Austerity Index (%)")

        # Austerity axis is contextual: keep labels, drop “precision” ticks so it
        # doesn’t fight the portfolio grid/ticks visually.
        ax2.yaxis.set_minor_locator(ticker.NullLocator())
        ax2.tick_params(axis="y", which="both", length=0)  # remove tick marks (“hatches”)

        # IMPORTANT: restore minor ticks/locators on the primary axis.
        # Some backends/locator interactions via twinx can clobber x minors.
        ax1.minorticks_on()
        ax1.xaxis.set_minor_locator(ticker.AutoMinorLocator())
        ax1.yaxis.set_minor_locator(ticker.AutoMinorLocator())

        # Make the right axis styling match the austerity line (subtle, readable)
        ax2.tick_params(axis='y', colors=austerity_color)
        ax2.yaxis.label.set_color(austerity_color)
        ax2.spines['right'].set_color(austerity_color)

    # Optional: event labels
    if event_labels:
        # Group events that occur in the same (integer) age year into one label line.
        # Also normalize + de-dupe so "Inflation Spike" and "[Inflation Spike]" collapse.
        events_by_year: dict[int, list[str]] = defaultdict(list)
        seen_by_year: dict[int, set[str]] = defaultdict(set)

        for age, label in event_labels:
            year_bucket = int(age)
            raw = "" if label is None else str(label).strip()
            if not raw:
                continue

            # Canonicalize so "[X]" and "X" are treated as the same event.
            canon = raw
            if canon.startswith("[") and canon.endswith("]"):
                canon = canon[1:-1].strip()

            if canon in seen_by_year[year_bucket]:
                continue
            seen_by_year[year_bucket].add(canon)
            events_by_year[year_bucket].append(canon)

        # Small x-offset “lanes” for dense clusters of adjacent years.
        buckets = sorted(events_by_year.keys())
        lane_offset: dict[int, int] = {}
        lane = 0
        prev = None
        for b in buckets:
            if prev is None:
                lane = 0
            else:
                lane = (lane + 1) % 3 if (b - prev) == 1 else 0
            lane_offset[b] = lane
            prev = b

        offsets = {0: 0.0, 1: 0.18, 2: -0.18}

        for year_bucket in buckets:
            label = _format_event_brackets(events_by_year[year_bucket])
            if not label:
                continue
            x_text = year_bucket + offsets.get(lane_offset.get(year_bucket, 0), 0.0)
            ax1.axvline(x=year_bucket, linestyle="--", color="black", alpha=0.3)
            ax1.text(x_text, ax1.get_ylim()[1] * 0.95, label, rotation=90,
                     verticalalignment='top', fontsize=8, color="black")

    ax1.set_title(f"{user_name} – {description}")
    ax1.set_xlabel("Age")
    ax1.set_ylabel("Portfolio Value ($ millions)")
    # Keep x/y labels readable and consistent across backends
    ax1.tick_params(axis="both", which="both", direction="out")

    # Legend: fixed, reproducible placement (no auto-avoid jumping around)
    ax1.legend(
        loc="lower right",
        framealpha=0.85,
    )

    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    # Prefer fig.savefig so we honor the figure's constrained_layout settings.
    fig.savefig(save_path)
    plt.close()
    print(f"Saved graph to {save_path}")
