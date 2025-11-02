#!/usr/bin/env python3
"""
Simple Tk/Tkinter front end for the retirement simulator.

Features:
- Select base user JSON (—user equivalent)
- List scenarios in data/ and open/edit them
- Edit/save JSON in an integrated editor with validation
- Run simulation for a selected scenario using your existing pipeline
"""

import os
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import traceback

# Project-relative imports (these already exist in your repo)
# run_and_display wraps validation, normalization, simulation, CSV + graph output
from run_all_simulations import run_and_display, DATA_DIR, OUTPUT_DIR  # :contentReference[oaicite:0]{index=0}
from engine.user_data_validation import validate_user_data              # :contentReference[oaicite:1]{index=1}

from json_form_editor import JsonEditorFrame, USER_SCHEMA_GUESS, SCENARIO_SCHEMA_GUESS

# Defaults
DEFAULT_DATA_DIR = DATA_DIR if os.path.isdir(DATA_DIR) else "data"
DEFAULT_OUTPUT_DIR = OUTPUT_DIR if os.path.isdir(OUTPUT_DIR) else "out"

MC_MODES = ("off", "sim", "events", "force")
GRANULARITY = ("monthly", "yearly")

def is_scenario_json(path):
    """Heuristic: scenario files must contain 'description', 'life_events', 'assumptions'."""
    try:
        with open(path, "r") as f:
            j = json.load(f)
        return isinstance(j, dict) and all(k in j for k in ("description", "life_events", "assumptions"))
    except Exception:
        return False

def is_user_json(path):
    """Heuristic: base user file must include person/expenses/income/portfolio."""
    try:
        with open(path, "r") as f:
            j = json.load(f)
        return isinstance(j, dict) and all(k in j for k in ("person", "expenses", "income", "portfolio"))
    except Exception:
        return False

class JsonEditorPane(ttk.Frame):
    """
    Thin wrapper that holds a JsonEditorFrame and exposes set_data/get_data.
    """
    def __init__(self, master):
        super().__init__(master)
        self.editor = None
        self.current_schema = None
        self.current_data = None

    def open(self, data: dict, schema: dict):
        for w in self.winfo_children():
            w.destroy()
        self.current_schema = schema
        self.current_data = data
        self.editor = JsonEditorFrame(self, data=data, schema=schema)
        self.editor.pack(fill="both", expand=True)

    def get_data(self):
        if self.editor:
            return self.editor.get_value()
        return None

class GUI(tk.Tk):
    def __init__(self, preset_user=None):
        super().__init__()
        self.title("Retirement Simulator – GUI")
        self.geometry("1100x700")

        # State
        self.data_dir = DEFAULT_DATA_DIR
        self.output_dir = DEFAULT_OUTPUT_DIR
        self.base_user_path = None
        self.current_edit_path = None
        self.current_edit_kind = None  # "user" | "scenario"

        # Options
        self.var_mc = tk.StringVar(value="force")
        self.var_gran = tk.StringVar(value="monthly")
        self.var_print = tk.BooleanVar(value=False)
        self.var_open = tk.BooleanVar(value=False)

        # Layout
        self._build_menu()
        self._build_main()

        # Preload
        self._refresh_scenario_list()
        if preset_user and os.path.exists(preset_user) and is_user_json(preset_user):
            self._select_user(preset_user)
        else:
            # Best effort: look for something like 'firstname_lastname.json' in data/
            guess = os.path.join(self.data_dir, "firstname_lastname.json")
            if os.path.exists(guess) and is_user_json(guess):
                self._select_user(guess)

    # ---------------- UI BUILDERS ----------------
    def _build_menu(self):
        menubar = tk.Menu(self)

        # File
        m_file = tk.Menu(menubar, tearoff=0)
        m_file.add_command(label="Select Base User…", command=self._menu_select_user)
        m_file.add_command(label="Save Current File", command=self._menu_save_current)
        m_file.add_separator()
        m_file.add_command(label="Run Simulation for Selected Scenario", command=self._run_selected_scenario)
        m_file.add_separator()
        m_file.add_command(label="Exit", command=self.destroy)
        menubar.add_cascade(label="File", menu=m_file)

        # Scenarios
        m_scn = tk.Menu(menubar, tearoff=0)
        m_scn.add_command(label="New Scenario (from template)", command=self._menu_new_scenario)
        m_scn.add_command(label="Open/Edit Selected Scenario", command=self._open_selected_scenario)
        m_scn.add_command(label="Duplicate Selected Scenario", command=self._duplicate_selected_scenario)
        m_scn.add_command(label="Delete Selected Scenario", command=self._delete_selected_scenario)
        menubar.add_cascade(label="Scenarios", menu=m_scn)

        # Options
        m_opt = tk.Menu(menubar, tearoff=0)
        m_opt.add_cascade(label="Monte Carlo Mode", menu=self._submenu_mc(m_opt))
        m_opt.add_cascade(label="Granularity", menu=self._submenu_granularity(m_opt))
        m_opt.add_checkbutton(label="Print table output to console", variable=self.var_print)
        m_opt.add_checkbutton(label="Auto-open PNG after run", variable=self.var_open)
        menubar.add_cascade(label="Options", menu=m_opt)

        # Help
        m_help = tk.Menu(menubar, tearoff=0)
        m_help.add_command(label="About", command=lambda: messagebox.showinfo(
            "About",
            "Retirement Simulator GUI\nUses your existing engine:\n- run_all_simulations.run_and_display\n- user_data_validation.validate_user_data"
        ))
        menubar.add_cascade(label="Help", menu=m_help)

        self.config(menu=menubar)

    def _submenu_mc(self, parent):
        m = tk.Menu(parent, tearoff=0)
        for mode in MC_MODES:
            m.add_radiobutton(label=mode, variable=self.var_mc, value=mode)
        return m

    def _submenu_granularity(self, parent):
        m = tk.Menu(parent, tearoff=0)
        for g in GRANULARITY:
            m.add_radiobutton(label=g, variable=self.var_gran, value=g)
        return m

    def _build_main(self):
        # Left: scenarios list + actions
        left = ttk.Frame(self)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=8)

        ttk.Label(left, text="Scenarios in data/:").pack(anchor="w")
        self.listbox = tk.Listbox(left, height=30, exportselection=False)
        self.listbox.pack(fill=tk.Y, expand=True)
        self.listbox.bind("<Double-Button-1>", lambda e: self._open_selected_scenario())

        btns = ttk.Frame(left)
        btns.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(btns, text="Open/Edit", command=self._open_selected_scenario).pack(side=tk.LEFT, padx=2)
        ttk.Button(btns, text="Run", command=self._run_selected_scenario).pack(side=tk.LEFT, padx=2)

        # Right: editor + status
        right = ttk.Frame(self)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Status row (selected user + options)
        status = ttk.Frame(right)
        status.pack(fill=tk.X)
        self.lbl_user = ttk.Label(status, text="Base user: (none selected)", foreground="#444")
        self.lbl_user.pack(side=tk.LEFT)

        opts = ttk.Frame(status)
        opts.pack(side=tk.RIGHT)
        ttk.Label(opts, text="MC:").pack(side=tk.LEFT)
        ttk.OptionMenu(opts, self.var_mc, self.var_mc.get(), *MC_MODES).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Label(opts, text="Granularity:").pack(side=tk.LEFT)
        ttk.OptionMenu(opts, self.var_gran, self.var_gran.get(), *GRANULARITY).pack(side=tk.LEFT)

        # Editor area
        self.form = JsonEditorPane(right)
        self.form.pack(fill=tk.BOTH, expand=True, pady=(6, 6))

        # Bottom action buttons
        bottom = ttk.Frame(right)
        bottom.pack(fill=tk.X)
        ttk.Button(bottom, text="Open Base User", command=self._open_base_user).pack(side=tk.LEFT, padx=2)
        ttk.Button(bottom, text="Save Current File", command=self._menu_save_current).pack(side=tk.LEFT, padx=2)
        ttk.Button(bottom, text="Run (Selected Scenario)", command=self._run_selected_scenario).pack(side=tk.RIGHT, padx=2)

    # ---------------- Actions ----------------
    def _refresh_scenario_list(self):
        self.listbox.delete(0, tk.END)
        if not os.path.isdir(self.data_dir):
            return
        for name in sorted(os.listdir(self.data_dir)):
            if not name.endswith(".json"):
                continue
            path = os.path.join(self.data_dir, name)
            if is_scenario_json(path):
                self.listbox.insert(tk.END, name)

    def _select_user(self, path):
        self.base_user_path = path
        self.lbl_user.config(text=f"Base user: {os.path.basename(path)}")

    def _menu_select_user(self):
        path = filedialog.askopenfilename(
            title="Select Base User JSON",
            initialdir=self.data_dir,
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if path and is_user_json(path):
            self._select_user(path)
        elif path:
            messagebox.showerror("Invalid", "This file doesn't look like a base user JSON.")

    def _open_base_user(self):
        if not self.base_user_path:
            messagebox.showwarning("No user", "Select a base user JSON first (File → Select Base User…).")
            return
        try:
            self._open_in_editor(self.base_user_path, kind="user")
        except Exception as e:
            messagebox.showerror("Open error", str(e))

    def _open_selected_scenario(self):
        sel = self._selected_scenario_name()
        if not sel:
            messagebox.showwarning("No selection", "Pick a scenario in the list.")
            return
        path = os.path.join(self.data_dir, sel)
        try:
            self._open_in_editor(path, kind="scenario")
        except Exception as e:
            messagebox.showerror("Open error", str(e))

    def _duplicate_selected_scenario(self):
        sel = self._selected_scenario_name()
        if not sel:
            messagebox.showwarning("No selection", "Pick a scenario in the list.")
            return
        src = os.path.join(self.data_dir, sel)
        base, ext = os.path.splitext(sel)
        dst_name = base + "_copy" + ext
        dst = os.path.join(self.data_dir, dst_name)
        i = 1
        while os.path.exists(dst):
            dst_name = f"{base}_copy{i}{ext}"
            dst = os.path.join(self.data_dir, dst_name)
            i += 1
        try:
            with open(src, "r") as f:
                data = json.load(f)
            with open(dst, "w") as f:
                json.dump(data, f, indent=2)
            self._refresh_scenario_list()
            self._select_listbox_item(dst_name)
            messagebox.showinfo("Duplicated", f"Created {dst_name}.")
        except Exception as e:
            messagebox.showerror("Duplicate error", str(e))

    def _delete_selected_scenario(self):
        sel = self._selected_scenario_name()
        if not sel:
            messagebox.showwarning("No selection", "Pick a scenario in the list.")
            return
        path = os.path.join(self.data_dir, sel)
        if not messagebox.askyesno("Confirm delete", f"Delete scenario '{sel}'?"):
            return
        try:
            os.remove(path)
            self._refresh_scenario_list()
            self.editor.delete("1.0", tk.END)
            if self.current_edit_path == path:
                self.current_edit_path = None
                self.current_edit_kind = None
        except Exception as e:
            messagebox.showerror("Delete error", str(e))

    def _menu_new_scenario(self):
        """Create a minimal scenario skeleton."""
        tpl = {
            "description": "New Scenario",
            "life_events": [],
            "assumptions": {
                "expected_return": 0.06,
                "variance": 0.02,
                "inflation": 0.025
            }
        }
        # Ask for a filename
        path = filedialog.asksaveasfilename(
            title="Save New Scenario As",
            initialdir=self.data_dir,
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")]
        )
        if not path:
            return
        try:
            with open(path, "w") as f:
                json.dump(tpl, f, indent=2)
            self._refresh_scenario_list()
            self._open_in_editor(path, kind="scenario")
            self._select_listbox_item(os.path.basename(path))
        except Exception as e:
            messagebox.showerror("Create error", str(e))

    def _menu_save_current(self):

        if not self.current_edit_path:
            messagebox.showwarning("Nothing to save", "Open a user or scenario JSON first.")
            return
        try:
            data = self.form.get_data()
            if data is None:
                raise ValueError("No data in editor.")
            if not isinstance(data, dict) or len(data) == 0:
                messagebox.showerror(
                    "Save aborted",
                    "The editor returned an empty object. Your file was NOT overwritten.\n"
                    "Please report this so we can fix the editor merge."
                )
                return

        except Exception as e:
            messagebox.showerror("Editor error", f"Could not read form data: {e}")
            return
        # (validation + write to disk continues unchanged)

        # Validate if possible
        if self.current_edit_kind == "scenario":
            if not self.base_user_path:
                messagebox.showwarning("No user selected",
                                       "Select a base user JSON before saving a scenario (enables validation).")
            else:
                # Write to a temp, validate with your existing validator (base+scenario)  :contentReference[oaicite:2]{index=2}
                import tempfile
                with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as tmp:
                    json.dump(data, tmp, indent=2)
                    tmp.flush()
                    tmp_path = tmp.name
                ok = validate_user_data(self.base_user_path, tmp_path)
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
                if not ok:
                    if not messagebox.askyesno("Validation failed",
                                               "Scenario failed validation. Save anyway?"):
                        return

        # Save
        try:
            with open(self.current_edit_path, "w") as f:
                json.dump(data, f, indent=2)
            messagebox.showinfo("Saved", f"Wrote {self.current_edit_path}")
            if self.current_edit_kind == "scenario":
                self._refresh_scenario_list()
        except Exception as e:
            messagebox.showerror("Save error", str(e))

    def _run_selected_scenario(self):
        sel = self._selected_scenario_name()
        if not self.base_user_path:
            messagebox.showwarning("No base user", "Select a base user JSON first (File → Select Base User…).")
            return
        if not sel:
            messagebox.showwarning("No scenario", "Pick a scenario in the list to run.")
            return
        scenario_path = os.path.join(self.data_dir, sel)

        # Final validation (base+scenario) and run via your existing pipeline  :contentReference[oaicite:3]{index=3}
        try:
            ok = validate_user_data(self.base_user_path, scenario_path)   # :contentReference[oaicite:4]{index=4}
            if not ok:
                if not messagebox.askyesno("Validation failed",
                                           "Validation failed. Run anyway?"):
                    return
            # Calls down to: load_user_data → normalize → simulate → CSV+graph+MC  :contentReference[oaicite:5]{index=5}
            run_and_display(
                base_filepath=self.base_user_path,
                scenario=scenario_path,
                print_output=self.var_print.get(),
                open_graph=self.var_open.get(),
                granularity=self.var_gran.get(),
                montecarlo_mode=self.var_mc.get(),
            )
            messagebox.showinfo("Done", f"Simulation complete.\nSee output in: {self.output_dir}")
        except Exception as e:
            tb = traceback.format_exc()
            messagebox.showerror("Run error", f"{e}\n\n{tb}")

    # ---------------- Helpers ----------------
    def _selected_scenario_name(self):
        sel = self.listbox.curselection()
        if not sel:
            return None
        return self.listbox.get(sel[0])

    def _open_in_editor(self, path, kind):
        import json
        with open(path, "r") as f:
            data = json.load(f)
            schema = USER_SCHEMA_GUESS if kind == "user" else SCENARIO_SCHEMA_GUESS
            self.form.open(data, schema)
            self.current_edit_path = path
            self.current_edit_kind = kind
            base = os.path.basename(path)
            self.title(f"Retirement Simulator – {base} [{kind}]")
    
    def _select_listbox_item(self, name):
        for i in range(self.listbox.size()):
            if self.listbox.get(i) == name:
                self.listbox.selection_clear(0, tk.END)
                self.listbox.selection_set(i)
                self.listbox.see(i)
                return

# --------------- CLI entry point ---------------
def main():
    import argparse
    parser = argparse.ArgumentParser(description="GUI for the retirement simulator.")
    parser.add_argument("--user", help="Preselect a base user JSON file", default=None)
    args = parser.parse_args()

    app = GUI(preset_user=args.user)
    app.mainloop()

if __name__ == "__main__":
    main()

