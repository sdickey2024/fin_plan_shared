# run_all_simulations.py

import os
import argparse
import subprocess
import sys
import matplotlib
from debug import *
from data.normalize import normalize_user_data_events

matplotlib.use('TkAgg')

from engine.retirement_simulator import (
    load_user_data,
    simulate_retirement,
    run_monte_carlo,
    run_monte_carlo_events,
    run_monte_carlo_force,
    get_event_age
)
from engine.user_data_validation import validate_user_data
from engine.display_results import (
    print_simulation,
    print_simulation_csv,
    graph_simulation_with_montecarlo
)

import matplotlib.pyplot as plt

OUTPUT_DIR = "out"
os.makedirs(OUTPUT_DIR, exist_ok=True)

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

def collect_event_labels(user_data):
    event_labels = []
    current_age = user_data["person"]["current_age"]
    for event in user_data.get("life_events", []):
        age = get_event_age(event["date"], current_age)
        label = event.get("event", "")
        if label:
            event_labels.append((age, label))
    return event_labels

def run_and_display(base_filepath, scenario, print_output=False, open_graph=False, granularity='monthly', montecarlo_mode='events'):
    print(f"\n=== Running simulation for: {base_filepath} + {scenario} ===")
    if not validate_user_data(base_filepath, scenario):
        print("Validation failed. Skipping this file.")
        return

    # load the data, combining the user (base) and scenario json files
    data = load_user_data(base_filepath, scenario)

    # normalize the data so that all events have all keys
    normalize_user_data_events(data)

    # create a base name from the scenario
    base_name = os.path.splitext(os.path.basename(scenario))[0]
    events_prefix = os.path.join(DATA_DIR, base_name)
    events_out = f"{events_prefix}.csv"
    
    dump_events_to_csv(data, events_out);

    # simulate the retirement scenario
    simulations = simulate_retirement(data, granularity=granularity)

    csv_prefix = os.path.join(OUTPUT_DIR, base_name)
    print_simulation_csv(simulations, filename_prefix=csv_prefix, granularity=granularity)

    if print_output:
        print_simulation(simulations, granularity=granularity)

    user_name = data.get("person", {}).get("name", "User")
    description = data.get("description", "Retirement Projection")

    print("Generating graph with Monte Carlo analysis...")
    if montecarlo_mode == 'off':
        print("Skipping Montecarlo...")                
        ages = []
        mc_percentiles = ([], [], [])
        mc_sample_run = None
    elif montecarlo_mode == 'sim':
        print("Running Montecarlo SIM...")        
        ages, mc_percentiles = run_monte_carlo(data, granularity=granularity)
        mc_sample_run = None
    elif montecarlo_mode == 'events':
        print("Running Montecarlo EVENTS...")
        ages, mc_percentiles, mc_sample_run = run_monte_carlo_events(data, granularity=granularity)
    else: # 'force'
        print("Running Montecarlo FORCE...")
        ages, mc_percentiles, mc_sample_run = run_monte_carlo_force(data, granularity=granularity)

    event_labels = collect_event_labels(data) if montecarlo_mode != 'off' else None

    graph_file = os.path.join(OUTPUT_DIR, f"{base_name}.png")
    graph_simulation_with_montecarlo(simulations, ages, mc_percentiles,
                                     user_name=user_name,
                                     description=description,
                                     save_path=graph_file,
                                     mc_sample_run=mc_sample_run,
                                     event_labels=event_labels)

    if open_graph:
        try:
            if sys.platform.startswith('darwin'):
                subprocess.call(('open', graph_file))
            elif os.name == 'nt':
                os.startfile(graph_file)
            elif os.name == 'posix':
                subprocess.call(('xdg-open', graph_file))
        except Exception as e:
            print(f"Failed to open graph: {e}")

def main():
    parser = argparse.ArgumentParser(description="Run all retirement simulations in the data folder.")
    parser.add_argument("-p", "--print", action="store_true", help="Print the final output to screen")
    parser.add_argument("-o", "--open", action="store_true", help="Open PNG output after generation")
    parser.add_argument("-u", "--user", help="User File to Process (must be in 'data' folder)")
    parser.add_argument("-f", "--file", help="Process only one specific data file (must be in 'data' folder)")
    parser.add_argument("-g", "--granularity", choices=["monthly", "yearly"], default="monthly", help="Granularity of simulation (monthly or yearly)")
    parser.add_argument("-m", "--montecarlo", choices=["off", "sim", "events", "force"], default="force", help="Monte Carlo mode: off, sim, events or force")
    parser.add_argument("-d", "--debug", choices=["error", "warn", "info", "vrbs", "vvrbs", "vvvrbs"], help="Debug verbosity level", default="info")

    args = parser.parse_args()

    # set the debug level
    if args.debug:
        level_map = {
            "error": ERROR,
            "warn": WARNING,
            "info": INFO,
            "vrbs": VERBOSE,
            "vvrbs": VVERBOSE,
            "vvvrbs": VVVERBOSE,
        }
        set_debug_level(level_map[args.debug])

    base_path = "data"
    if args.file:
        files_to_process = [args.file] if os.path.exists(os.path.join(base_path, args.file)) else []
    else:
        files_to_process = [f for f in os.listdir(base_path) if f.endswith(".json")]

    if not args.user:
        print(f"User --user option requred")
        return

    for scenario in files_to_process:
        run_and_display(os.path.join(base_path, args.user),
                        os.path.join(base_path, scenario),
                        print_output=args.print,
                        open_graph=args.open,
                        granularity=args.granularity,
                        montecarlo_mode=args.montecarlo)

if __name__ == "__main__":
    main()
