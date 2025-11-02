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

def print_simulation(simulations, granularity='monthly'):
    for scenario, results in simulations.items():
        print(f"\n--- {scenario.upper()} RETURN SCENARIO ---")
        print(f"{'Age':<8}{'Month':<6}{'Year':<8}{'Portfolio':>17}{'Income':>12}"
              f"{'Taxed Income':>16}{'Monthly Raw Exp.':>20}{'Raw Exp.':>15}"
              f"{'Net Exp.':>15}{'Gross Up':>15}     {'Event'}")
        for year_data in results:
            if granularity == 'yearly' and year_data['month'] != 1:
                continue
            print(f"{year_data['age']:>6.2f}  {year_data['month']:<6}{year_data['year']:<8}"
                  f"${year_data['portfolio_end']:>15,.2f}"
                  f"${year_data['income']:>11,.2f}"
                  f"${year_data['taxed_income']:>15,.2f}"
                  f"${year_data['monthly_raw_expenses']:>19,.2f}"
                  f"${year_data['raw_expenses']:>14,.2f}"
                  f"${year_data['net_expenses']:>14,.2f}"
                  f"${year_data['gross_up']:>14,.2f}     "
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

def graph_simulation_with_montecarlo(simulations, ages, mc_percentiles, user_name="User", description="Simulation", save_path="out/simulation.png", mc_sample_run=None, event_labels=None):
    plt.figure(figsize=(12, 6))

    # Simulation lines
    for label, results in simulations.items():
        age_vals = [entry["age"] for entry in results]
        values = [entry["portfolio_end"] / 1_000_000 for entry in results]
        plt.plot(age_vals, values, label=f"{label.capitalize()} Return")

    # Monte Carlo envelope and median
    median = np.array(mc_percentiles[1]) / 1_000_000
    p10 = np.array(mc_percentiles[0]) / 1_000_000
    p90 = np.array(mc_percentiles[2]) / 1_000_000

    plt.plot(ages, median, label="Monte Carlo Median", linestyle='--')
    plt.fill_between(ages, p10, p90, color='gray', alpha=0.3, label="10th-90th Percentile Range")

    # Optional: a sample Monte Carlo run
    if mc_sample_run:
        sample_ages = [point["age"] for point in mc_sample_run]
        sample_vals = [point.get("portfolio", point.get("portfolio_value", 0)) / 1_000_000 for point in mc_sample_run]
        plt.plot(sample_ages, sample_vals, linestyle=':', linewidth=1.5, label="Sample MC Run")

    # Optional: event labels
    if event_labels:
        for age, label in event_labels:
            plt.axvline(x=age, linestyle="--", color="black", alpha=0.3)
            plt.text(age, plt.ylim()[1] * 0.95, label, rotation=90, verticalalignment='top', fontsize=8, color="black")

    plt.title(f"{user_name} – {description}")
    plt.xlabel("Age")
    plt.ylabel("Portfolio Value ($ millions)")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path)
    plt.close()
    print(f"Saved graph to {save_path}")
