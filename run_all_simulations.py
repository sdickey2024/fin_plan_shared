# run_all_simulations.py

import os
import argparse
import subprocess
import sys
import matplotlib
from concurrent.futures import ProcessPoolExecutor, as_completed
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

def _configure_matplotlib(backend: str):
    """
    Must be called BEFORE importing pyplot in the process where it matters.
    In this file pyplot is imported at module import time, so we set the backend
    as early as possible (and again inside worker processes).
    """
    try:
        matplotlib.use(backend, force=True)
    except Exception:
        pass

OUTPUT_DIR = "out"
os.makedirs(OUTPUT_DIR, exist_ok=True)

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

# New hierarchy
USER_BASE_DIR = os.path.join(DATA_DIR, "user_base")
SCENARIO_DIR = os.path.join(DATA_DIR, "scenarios")
os.makedirs(USER_BASE_DIR, exist_ok=True)
os.makedirs(SCENARIO_DIR, exist_ok=True)

def collect_event_labels(user_data):
    event_labels = []
    current_age = user_data["person"]["current_age"]
    for event in user_data.get("life_events", []):
        age = get_event_age(event["date"], current_age)
        label = event.get("event", "")
        if label:
            event_labels.append((age, label))
    return event_labels

def _worker_run_one(args_tuple):
    """
    Top-level function so it's picklable for multiprocessing.
    args_tuple: (base_filepath, scenario, print_output, open_graph, granularity, montecarlo_mode)
    """
    # In a worker process: force non-GUI backend.
    _configure_matplotlib("Agg")
    base_filepath, scenario, print_output, open_graph, granularity, montecarlo_mode = args_tuple
    try:
        run_and_display(
            base_filepath=base_filepath,
            scenario=scenario,
            print_output=print_output,
            open_graph=open_graph,   # should be False in parallel
            granularity=granularity,
            montecarlo_mode=montecarlo_mode,
        )
        return (scenario, True, "")
    except Exception as e:
        return (scenario, False, str(e))

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

def _resolve_user_path(user_arg: str) -> str:
    """
    Resolve --user argument.
    Accept absolute/existing paths; otherwise look in data/user_base/ then data/.
    """
    if os.path.isabs(user_arg) or os.path.exists(user_arg):
        return user_arg
    cand = os.path.join(USER_BASE_DIR, user_arg)
    if os.path.exists(cand):
        return cand
    cand2 = os.path.join(DATA_DIR, user_arg)
    return cand2

def _resolve_scenario_path(s: str) -> str:
    """
    Resolve a scenario spec from --file.
    Accept absolute/existing paths; otherwise look in data/scenarios/ then data/.
    """
    if os.path.isabs(s) or os.path.exists(s):
        return s
    cand = os.path.join(SCENARIO_DIR, s)
    if os.path.exists(cand):
        return cand
    cand2 = os.path.join(DATA_DIR, s)
    return cand2

            
def main():
    parser = argparse.ArgumentParser(description="Run all retirement simulations in the data folder.")
    parser.add_argument("-p", "--print", action="store_true", help="Print the final output to screen")
    parser.add_argument("-o", "--open", action="store_true", help="Open PNG output after generation")
    parser.add_argument("-u", "--user", help="User File to Process (must be in 'data' folder)")
    parser.add_argument("-f", "--file", action="append",
                        help="Process only specific scenario file(s). Repeatable: --file A.json --file B.json (also supports comma-separated).")
    parser.add_argument("-g", "--granularity", choices=["monthly", "yearly"], default="monthly", help="Granularity of simulation (monthly or yearly)")
    parser.add_argument("-m", "--montecarlo", choices=["off", "sim", "events", "force"], default="force", help="Monte Carlo mode: off, sim, events or force")
    parser.add_argument("-j", "--jobs", type=int, default=8, help="Number of parallel worker processes (1 = serial)")
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

    if args.file:
        # args.file is repeatable; also allow comma-separated entries
        requested = []
        for item in args.file:
            if not item:
                continue
            parts = [p.strip() for p in item.split(",") if p.strip()]
            requested.extend(parts)

        scenario_paths = []
        missing = []
        for f in requested:
            cand = _resolve_scenario_path(f)
            if os.path.exists(cand):
                scenario_paths.append(cand)
            else:
                missing.append(f)

        if missing:
            print(f"ERROR: One or more --file entries not found: {missing}")
            return
    else:
        # Default: all scenarios in data/scenarios/
        scenario_paths = [
            os.path.join(SCENARIO_DIR, f)
            for f in os.listdir(SCENARIO_DIR)
            if f.endswith(".json")
        ]

    if not args.user:
        print(f"User --user option requred")
        return

    # Backend choice:
    # - serial + open windows => TkAgg is fine
    # - parallel => must be non-GUI
    if args.jobs and args.jobs > 1:
        _configure_matplotlib("Agg")
    else:
        _configure_matplotlib("TkAgg")

    base_user_path = _resolve_user_path(args.user)

    # Parallel mode: never auto-open graphs.
    open_graph = bool(args.open) and (not args.jobs or args.jobs <= 1)

    if args.jobs and args.jobs > 1 and len(scenario_paths) > 1:
        jobs = max(1, int(args.jobs))
        work = [
            (base_user_path, sp, args.print, False, args.granularity, args.montecarlo)
            for sp in scenario_paths
        ]
        print(f"Running {len(work)} scenario(s) with {jobs} parallel worker(s)...")
        failures = 0
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            futs = [ex.submit(_worker_run_one, w) for w in work]
            for fut in as_completed(futs):
                scen, ok, err = fut.result()
                if ok:
                    print(f"[OK]   {os.path.basename(scen)}")
                else:
                    failures += 1
                    print(f"[FAIL] {os.path.basename(scen)}: {err}")
        if failures:
            print(f"\nDone with {failures} failure(s).")
        else:
            print("\nDone. All scenarios succeeded.")
    else:
        for sp in scenario_paths:
            run_and_display(base_user_path,
                            sp,
                            print_output=args.print,
                            open_graph=open_graph,
                            granularity=args.granularity,
                            montecarlo_mode=args.montecarlo)

if __name__ == "__main__":
    main()
