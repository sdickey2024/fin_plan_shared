#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import json
import traceback
import io
import re
import html
import contextlib
from typing import Optional, List
import subprocess
import shutil
import shlex

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QMessageBox,
    QWidget, QVBoxLayout, QSplitter, QPlainTextEdit, QToolBar, QLabel, QTabWidget,
    QTextBrowser
)
from PySide6.QtWidgets import QTextEdit
from PySide6.QtGui import QAction, QTextCursor, QTextCharFormat, QColor, QPalette
from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QScrollArea

from .editor_panel import EditorPanel
from .scenario_panel import ScenarioPanel
from .run_panel import RunPanel, RunWorker

import subprocess
import shutil
import time

# Use engine constants if available
try:
    from run_all_simulations import DATA_DIR, OUTPUT_DIR
except Exception:
    DATA_DIR, OUTPUT_DIR = "data", "out"

# Split base files vs scenario files
BASE_DIR = os.path.join(DATA_DIR, "user_base")
SCENARIO_DIR = os.path.join(DATA_DIR, "scenarios")

class MainWindow(QMainWindow):
    APP_NAME = "fin_plan"
    VERSION = "1.0.0"

    def __init__(self):
        super().__init__()
        self.setWindowTitle("fin_plan – Qt GUI")
        self.resize(1400, 900)

        self.base_path: Optional[str] = None
        self.scenario_path: Optional[str] = None
        self._dirty = False
        self._scenario_dirty = False

        # Toolbar (status only)
        tb = QToolBar("Main")
        self.addToolBar(tb)

        # Toolbar status (Base + Scenario)
        self.lbl_status = QLabel("Base: (none)\nScenario: (none)")
        self.lbl_status.setStyleSheet(
            "color: #f0c000; font-weight: bold; white-space: pre;"
        )
        tb.addWidget(self.lbl_status)

        # Actions (menus)
        act_open_base = QAction("Open Base…", self)
        act_open_scen = QAction("Open Scenario…", self)
        act_save_base = QAction("Save Base", self)
        act_save_base_as = QAction("Save Base As…", self)
        act_save_scen = QAction("Save Scenario", self)
        act_save_scen_as = QAction("Save Scenario As…", self)

        act_open_base.triggered.connect(self.open_base)
        act_open_scen.triggered.connect(self.open_scenario_dialog)
        act_save_base.triggered.connect(self.save_base)
        act_save_base_as.triggered.connect(self.save_base_as)
        act_save_scen.triggered.connect(self.save_scenario)
        act_save_scen_as.triggered.connect(self.save_scenario_as)

        # Menu Bar (File / View / Help)
        menubar = self.menuBar()

        # --- File menu -----------------------------------------------------
        m_file = menubar.addMenu("&File")

        m_file.addAction(act_open_base)
        m_file.addAction(act_open_scen)
        m_file.addSeparator()
        m_file.addAction(act_save_base)
        m_file.addAction(act_save_base_as)
       
        m_file.addSeparator()
        m_file.addAction(act_save_scen)
        m_file.addAction(act_save_scen_as)
        m_file.addSeparator()
        act_exit = QAction("E&xit", self)
        act_exit.triggered.connect(self.close)
        m_file.addAction(act_exit)

        # --- View menu -----------------------------------------------------
        m_view = menubar.addMenu("&View")
        self.act_show_log = QAction("Show &Log", self)
        self.act_show_log.setCheckable(True)
        self.act_show_log.setChecked(True)
        self.act_show_log.toggled.connect(self._set_log_visible)
        m_view.addAction(self.act_show_log)

        act_open_out = QAction("Open &Output Folder", self)
        act_open_out.triggered.connect(self.open_output_folder)
        m_view.addAction(act_open_out)

        act_refresh_scen = QAction("&Refresh Scenarios", self)
        act_refresh_scen.triggered.connect(self.refresh_scenarios)
        m_view.addAction(act_refresh_scen)

        # --- Tools menu ----------------------------------------------------
        m_tools = menubar.addMenu("&Tools")
        act_validate_all = QAction("&Validate Data Files…", self)
        act_validate_all.setStatusTip("Validate all base and scenario JSON files in the data folder")
        act_validate_all.triggered.connect(self.validate_data_files)
        m_tools.addAction(act_validate_all)

        # --- Help menu -----------------------------------------------------
        m_help = menubar.addMenu("&Help")
        act_help = QAction("&Documentation", self)
        act_help.triggered.connect(self.show_documentation)
        m_help.addAction(act_help)

        act_about = QAction("&About", self)
        act_about.triggered.connect(self.show_about)
        m_help.addAction(act_about)

        # Central layout
        central = QWidget()
        self.setCentralWidget(central)
        v = QVBoxLayout(central)
        v.setContentsMargins(0, 0, 0, 0)

        # Ensure expected data dirs exist
        os.makedirs(BASE_DIR, exist_ok=True)
        os.makedirs(SCENARIO_DIR, exist_ok=True)

        split = QSplitter(Qt.Horizontal)
        self.split = QSplitter(Qt.Horizontal)
        v.addWidget(self.split, 1)

        # Left: scenarios
        self.scenarios = ScenarioPanel(data_dir=SCENARIO_DIR)
        self.split.addWidget(self.scenarios)
        self.scenarios.setMinimumWidth(420)

        # Center: editor tabs (Base + Scenario)
        self.edit_tabs = QTabWidget()
        self.base_editor = EditorPanel()
        self.scen_editor = EditorPanel()
        self.edit_tabs.addTab(self.base_editor, "Base")
        self.edit_tabs.addTab(self.scen_editor, "Scenario")
        self.split.addWidget(self.edit_tabs)

        self.split.setStretchFactor(0, 0)
        self.split.setStretchFactor(1, 1)

        # Bottom: run controls + log
        self.run_panel = RunPanel()
        v.addWidget(self.run_panel, 0)

        # Use QTextEdit so we can colorize error output (red) in the log pane.
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setAcceptRichText(True)
        self.log.setUndoRedoEnabled(False)
        try:
            self.log.document().setMaximumBlockCount(2000)
        except Exception:
            pass

        # Log formatting: explicitly set BOTH default + error colors so we never
        # "inherit" a previous line's formatting (the source of the red-bleed).
        self._log_default_format = QTextCharFormat()
        self._log_error_format = QTextCharFormat()
        # A red that reads well on grey/dark backgrounds:
        self._log_error_format.setForeground(QColor("#ff6b6b"))

        # Use the widget's normal text color for "default" lines (theme-aware).
        default_fg = self.log.palette().color(QPalette.Text)
        self._log_default_format.setForeground(default_fg)

        # A red that reads well on grey/dark backgrounds:
        self._log_error_format.setForeground(QColor("#ff6b6b"))

        # Strip ANSI escape sequences (e.g. "\x1b[31m") from tool output.
        self._ansi_re = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

        v.addWidget(self.log, 0)
        self.log.setFixedHeight(220)

        self.base_editor.dirtyChanged.connect(self._set_dirty)
        self.scen_editor.dirtyChanged.connect(self._set_scenario_dirty)
        self.run_panel.runRequested.connect(self.run_selected)
        self.run_panel.openGraphsRequested.connect(self.open_graphs)
        self.scenarios.openRequested.connect(self.open_scenario)
        self.scenarios.preferredWidthChanged.connect(self._apply_scenarios_width)

        # Thread/worker
        self._thread: Optional[QThread] = None
        self._worker: Optional[RunWorker] = None

        # Startup hint
        self._append_log("Tip: Open a base JSON, then select scenarios on the left, then Run.")
        
    def _apply_scenarios_width(self, w: int):
        """
        After scenarios are populated, adjust the splitter so scenario labels
        are readable without manual resizing.
        """
        try:
            total = max(1, self.split.size().width())
            # Keep editor area dominant; clamp left width.
            left = max(320, min(int(w), total - 450))
            right = max(200, total - left)
            self.split.setSizes([left, right])
        except Exception:
            pass

    def _update_status_labels(self):
        base = os.path.basename(self.base_path) if self.base_path else "(none)"
        scen = os.path.basename(self.scenario_path) if self.scenario_path else "(none)"
        self.lbl_status.setText(f"Base: {base}\nScenario: {scen}")

    # ---------------------------------------------------------------------
    # Menu Actions
    # ---------------------------------------------------------------------
    def open_scenario_dialog(self):
        """
        File -> Open Scenario...
        This is a convenience path to open a scenario for editing without
        requiring a double-click in the scenario list.
        """
        path, _ = QFileDialog.getOpenFileName(self, "Open Scenario JSON", SCENARIO_DIR, "JSON (*.json)")
        if not path:
            return
        self.open_scenario(path)

    def validate_data_files(self):
        """Validate all base/scenario JSON files in the data folder.

        - Validates each JSON file individually (schema + life_event structural rules).
        - If a base is currently open, also validates that base against every scenario
          in the data folder (same check used before running).
        """
        try:
            from engine.user_data_validation import (
                validate_files_in_dir,
                validate_user_data,
            )
        except Exception:
            self._append_log("ERROR: Could not import validator module.")
            self._append_log(traceback.format_exc())
            QMessageBox.critical(self, "Validator import error", "Could not import validation module. See log.")
            return

        ok_paths, errors = validate_files_in_dir(DATA_DIR)

        # If a base is open, also validate base+scenario compatibility for all scenarios.
        if self.base_path and os.path.isfile(self.base_path):
            try:
                if os.path.isdir(SCENARIO_DIR):
                    scenario_paths = sorted(
                        os.path.join(SCENARIO_DIR, f)
                        for f in os.listdir(SCENARIO_DIR)
                        if f.lower().endswith(".json")
                    )
                else:
                    scenario_paths = []

                for p in scenario_paths:
                    if not validate_user_data(self.base_path, p):
                        errors.append(
                            f"{os.path.basename(self.base_path)} + {os.path.basename(p)}: failed base+scenario validation"
                        )
            except Exception:
                self._append_log("Warning: base+scenario validation pass failed.")
                self._append_log(traceback.format_exc())

        # Present results
        if errors:
            self._append_log("Validation failed for one or more files:")
            for e in errors[:200]:
                self._append_log("  " + e)
            if len(errors) > 200:
                self._append_log(f"  …and {len(errors) - 200} more")

            QMessageBox.warning(
                self,
                "Validation failed",
                "Found validation issues:\n\n"
                + "\n".join(errors[:80])
                + ("\n\n…(more in log)" if len(errors) > 80 else ""),
            )
            return

        QMessageBox.information(
            self,
            "Validation OK",
            f"All JSON files validated successfully.\n\nFiles checked: {len(ok_paths)}",
        )
        self._append_log(f"Validation OK: {len(ok_paths)} file(s) checked under {DATA_DIR}.")

    def _docs_path(self, name: str) -> str:
        """Return an absolute path to a docs file shipped with the GUI."""
        here = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(here, "docs", name)

    def _show_markdown_dialog(self, title: str, md_path: str, fallback_text: str):
        """Display a local Markdown file in a scrollable dialog."""
        md_path = os.path.abspath(md_path)

        # Load markdown (or fallback text) into a browser.
        if os.path.isfile(md_path):
            try:
                with open(md_path, "r", encoding="utf-8") as f:
                    md = f.read()
            except Exception as e:
                md = fallback_text + f"\n\nFailed to read:\n{md_path}\n\n{e}"
        else:
            md = fallback_text + f"\n\nMissing file:\n{md_path}"

        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(950, 750)

        layout = QVBoxLayout(dlg)
        browser = QTextBrowser(dlg)
        browser.setOpenExternalLinks(True)
        browser.setMarkdown(md)
        layout.addWidget(browser)

        dlg.exec()

    def show_documentation(self):
        self._show_markdown_dialog(
            title=f"{self.APP_NAME} Documentation",
            md_path=self._docs_path("help.md"),
            fallback_text="Documentation not found.",
        )

    def show_about(self):
        about_fallback = (
            f"# {self.APP_NAME}\n\n"
            "**Retirement & Financial Scenario Simulator**\n\n"
            f"Version **{self.VERSION}**\n\n"
            "Author: **Stephen Dickey**\n\n"
            "This software is provided for planning purposes only.\n"
            "It does not constitute financial advice.\n"
        )
        self._show_markdown_dialog(
            title=f"About {self.APP_NAME}",
            md_path=self._docs_path("about.md"),
            fallback_text=about_fallback,
        )

    def open_output_folder(self):
        out_dir = os.path.abspath(OUTPUT_DIR)
        if not os.path.isdir(out_dir):
            QMessageBox.information(self, "Output folder", f"No output directory:\n{out_dir}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(out_dir))

    def refresh_scenarios(self):
        if hasattr(self, "scenarios") and self.scenarios:
            self.scenarios.refresh()
        self._append_log("Refreshed scenario list.")

    def _set_log_visible(self, visible: bool):
        if not hasattr(self, "log") or not self.log:
            return
        self.log.setVisible(bool(visible))
        # Avoid layout jumpiness when hidden
        self.log.setFixedHeight(220 if visible else 0)

    def _append_log(self, msg: str):
        """
        Append a line to the GUI log.
        - Errors are colored red.
        - Everything else is default text color.
        """
        if not hasattr(self, "log") or not self.log:
            return

        # Support multi-line messages cleanly
        lines = str(msg).splitlines() or [""]
        for line in lines:
            self._append_log_line(line)

    def _sanitize_log_text(self, s: str) -> str:
        """
        Remove ANSI color codes and normalize line endings so classification is stable.
        """
        if s is None:
            return ""
        s = str(s)
        # Remove ANSI escape sequences
        s = self._ansi_re.sub("", s)
        # Normalize CRLF / stray CR
        s = s.replace("\r\n", "\n").replace("\r", "")
        return s

    def _append_formatted_line(self, s: str, fmt: QTextCharFormat) -> None:
        """Append a single line using an explicit QTextCharFormat (prevents color 'bleed')."""
        s = self._sanitize_log_text(s)
        if not s.endswith("\n"):
            s += "\n"

        cursor = self.log.textCursor()
        cursor.movePosition(QTextCursor.End)

        # Insert with explicit format
        cursor.insertText(s, fmt)

        # Reset to default format so subsequent inserts don't inherit color
        cursor.setCharFormat(self._log_default_format)
        self.log.setTextCursor(cursor)

    def _append_plain_line(self, s: str) -> None:
        self._append_formatted_line(s, self._log_default_format)

    def _append_error_line(self, s: str) -> None:
        self._append_formatted_line(s, self._log_error_format)

    def _append_log_line(self, line: str):
        s = self._sanitize_log_text(line)
        if "ERROR" in s:
            self._append_error_line(s)
        else:
            self._append_plain_line(s)

    def _set_dirty(self, dirty: bool):
        self._dirty = dirty
        self._refresh_title()

    def _set_scenario_dirty(self, dirty: bool):
        self._scenario_dirty = dirty
        self.edit_tabs.setTabText(1, "Scenario*" if dirty else "Scenario")

    def _refresh_title(self):
        star = "*" if self._dirty else ""
        base = os.path.basename(self.base_path) if self.base_path else "(none)"
        self.setWindowTitle(f"fin_plan – Qt GUI{star} — {base}")

    def maybe_save(self) -> bool:
        if not self._dirty:
            return True
        r = QMessageBox.question(
            self,
            "Unsaved changes",
            "Base JSON has unsaved changes. Save now?",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
        )
        if r == QMessageBox.Cancel:
            return False
        if r == QMessageBox.Yes:
            return self.save_base()
        return True

    def open_base(self):
        if not self.maybe_save():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open Base JSON", BASE_DIR, "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("Base JSON must be an object at the top level.")
            self.base_path = path
            self.base_editor.set_json(data)
            self.base_editor.set_clean()
            self._dirty = False
            self._refresh_title()
            self._update_status_labels()
            self.scenarios.set_base_path(self.base_path)
            # Make sure the left list repopulates immediately after base selection
            self.scenarios.refresh()
            self._append_log(f"Opened base: {self.base_path}")
        except Exception as e:
            QMessageBox.critical(self, "Open failed", str(e))

    def _commit_editor_edits(self, editor: EditorPanel):
        """
        Force any in-progress QTreeView edit to commit to the model before we read JSON.
        Without this, 'Save' can write the old value if the user hasn't pressed Enter
        or moved focus out of the edited cell.
        """
        try:
            tv = editor.tree_view
            # End any active edit session
            if tv.state() != tv.NoState:
                tv.closePersistentEditor(tv.currentIndex())
                tv.clearFocus()
                QApplication.processEvents()
        except Exception:
            pass

    def save_base(self) -> bool:
        if not self.base_path:
            return self.save_base_as()
        try:
            self.base_editor.commit_pending_edits()
            data = self.base_editor.get_json()
            with open(self.base_path, "w") as f:
                json.dump(data, f, indent=2)
            self.base_editor.set_clean()
            self._dirty = False
            self._refresh_title()
            self._append_log(f"Saved base: {self.base_path}")
            return True
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))
            return False

    def save_base_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(self, "Save Base JSON As", BASE_DIR, "JSON (*.json)")
        if not path:
            return False
        if not path.endswith(".json"):
            path += ".json"
        self.base_path = path
        self.lbl_base.setText(f"Base: {self.base_path}")
        self.lbl_base.setStyleSheet("color: black;")
        ok = self.save_base()
        self.scenarios.set_base_path(self.base_path)
        return ok

    def open_scenario(self, path: str):
        # If you want a "maybe save scenario" prompt later, add it here.
        try:
            with open(path, "r") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("Scenario JSON must be an object at the top level.")
            self.scenario_path = path
            self.scen_editor.set_json(data)
            self.scen_editor.set_clean()
            self._scenario_dirty = False
            self.edit_tabs.setTabText(1, "Scenario")
            self.edit_tabs.setCurrentIndex(1)
            self._update_status_labels()
            self._append_log(f"Opened scenario: {self.scenario_path}")
        except Exception as e:
            QMessageBox.critical(self, "Open scenario failed", str(e))

    def save_scenario(self) -> bool:
        if not self.scenario_path:
            return self.save_scenario_as()
        try:
            self.base_editor.commit_pending_edits()
            data = self.scen_editor.get_json()
            with open(self.scenario_path, "w") as f:
                json.dump(data, f, indent=2)
            self.scen_editor.set_clean()
            self._scenario_dirty = False
            self.edit_tabs.setTabText(1, "Scenario")
            self._append_log(f"Saved scenario: {self.scenario_path}")
            self.scenarios.refresh()  # update labels/tooltips (description etc.)
            return True
        except Exception as e:
            QMessageBox.critical(self, "Save scenario failed", str(e))
            return False

    def save_scenario_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(self, "Save Scenario As", SCENARIO_DIR, "JSON (*.json)")
        if not path:
            return False
        if not path.endswith(".json"):
            path += ".json"
        self.scenario_path = path
        return self.save_scenario()

    def _pick_png_to_open(self) -> Optional[str]:
        """
        Pick a single PNG inside OUTPUT_DIR. Opening one image lets the viewer
        navigate the rest in that folder (your < > arrows behavior).
        """
        out_dir = os.path.abspath(OUTPUT_DIR)
        if not os.path.isdir(out_dir):
            return None

        pngs: List[str] = []
        for root, _, files in os.walk(out_dir):
            for fn in files:
                if fn.lower().endswith(".png"):
                    pngs.append(os.path.join(root, fn))
        if not pngs:
            return None

        # Prefer most-recent
        pngs.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return pngs[0]

    def open_graphs(self):
        png = self._pick_png_to_open()
        if not png:
            QMessageBox.information(self, "No graphs found", f"No .png files found under: {OUTPUT_DIR}/")
            return

        self._append_log(f"Opening graphs via viewer: {png}")

        # You tested /usr/bin/open works best (gallery navigation).
        opener = "/usr/bin/open" if os.path.exists("/usr/bin/open") else None
        if opener:
            subprocess.Popen([opener, png])
            return

        # Fallbacks (in case /usr/bin/open isn't available)
        if shutil.which("xdg-open"):
            subprocess.Popen(["xdg-open", png])
            return

        QMessageBox.warning(self, "No opener", "Could not find /usr/bin/open or xdg-open to open images.")

    def run_selected(self):
        if not self.base_path:
            QMessageBox.warning(self, "No base file", "Open a base JSON first.")
            return
        # Must be saved (A choice)
        if self._dirty:
            r = QMessageBox.question(
                self, "Save required", "Base must be saved before running. Save now?",
                QMessageBox.Yes | QMessageBox.Cancel
            )
            if r != QMessageBox.Yes:
                return
            if not self.save_base():
                return

        scenarios = self.scenarios.selected_scenarios()
        if not scenarios:
            QMessageBox.information(self, "No scenarios selected", "Check one or more scenarios on the left.")
            return

        # Validate each scenario quickly before run (optional but useful)
        try:
            from engine.user_data_validation import validate_user_data
            bad = []
            details_by_path = {}
            for s in scenarios:
                # Capture validator stdout so we can show *why* it failed in the log pane.
                buf = io.StringIO()
                ok = True
                with contextlib.redirect_stdout(buf):
                    ok = bool(validate_user_data(self.base_path, s))
                out = buf.getvalue().strip()

                if not ok:
                    bad.append(s)
                    if out:
                        details_by_path[s] = out
            if bad:
                for path in bad:
                    self._log_validation_failure_details(
                        title="Validation failed:",
                        base_path=self.base_path,
                        scenario_path=path,
                        details=details_by_path.get(path, ""),
                    )
                QMessageBox.warning(
                    self, "Validation failed",
                    "One or more scenarios failed validation.\n\n" + "\n".join(bad)
                )
                return
        except Exception:
            # don't block runs if validator import fails; but log it
            self._append_log("Warning: validator check skipped due to import error.")
            self._append_log(traceback.format_exc())
        # Build CLI command (repeatable --file)
        user_arg = os.path.basename(self.base_path)
        file_args = []
        for s in scenarios:
            file_args += ["--file", s]

        # Map GUI mode to CLI --montecarlo
        mode = self.run_panel.montecarlo_mode()
        mc_arg = "events" if mode == "events" else "force"

        cmd = [
            sys.executable,
            os.path.join(os.getcwd(), "run_all_simulations.py"),
            "--user", user_arg,
            "--jobs", str(self.run_panel.jobs()),
            "--granularity", self.run_panel.granularity(),
            "--montecarlo", mc_arg,
        ] + file_args

        # Start worker thread
        if self._thread:
            QMessageBox.warning(self, "Busy", "A run is already in progress.")
            return

        self._run_started_ts = time.time()
        self.run_panel.set_running(True)
        self.run_panel.set_status("Running…")
        self._append_log(f"Running {len(scenarios)} scenario(s)…")

        self._thread = QThread()
        self._worker = RunWorker(
            cmd=cmd,
            cwd=os.getcwd(),
        )
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._append_log)
        self._worker.finished.connect(self._on_run_finished)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)

        self._thread.start()

    def _show_image_dialog(self, path: str):
        path = os.path.abspath(path)
        if not os.path.isfile(path):
            self._append_log(f"Not a file, cannot open: {path}")
            return

        pix = QPixmap(path)
        if pix.isNull():
            self._append_log(f"Could not load image: {path}")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(os.path.basename(path))
        dlg.resize(1100, 800)

        layout = QVBoxLayout(dlg)

        scroll = QScrollArea(dlg)
        scroll.setWidgetResizable(True)

        lbl = QLabel()
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setPixmap(pix)
        lbl.setScaledContents(False)

        scroll.setWidget(lbl)
        layout.addWidget(scroll)

        dlg.show()
        # keep a reference so it doesn't get GC'd
        if not hasattr(self, "_img_dialogs"):
            self._img_dialogs = []
        self._img_dialogs.append(dlg)


    def _on_run_finished(self, ok: bool, msg: str):
        if ok:
            self.run_panel.set_status("Done")
            self._append_log("Done.")
            # Tell user where outputs go (engine uses OUTPUT_DIR)
            self._append_log(f"Outputs: {OUTPUT_DIR}/")
            # Open a representative PNG; viewer can navigate all PNGs in folder
            self.open_graphs()
            
        # Graph viewing is handled exclusively by open_graphs() using /usr/bin/open.

        else:
            self.run_panel.set_status("Error")
            self._append_log("ERROR during run:")
            self._append_log(msg)
            QMessageBox.critical(self, "Run failed", "Run failed. See log pane for details.")

    def _log_validation_failure_details(self, title: str, base_path: str, scenario_path: Optional[str], details: str) -> None:
        """
        Log validation failures with *context* in normal text and only actual
        error lines in red. Also de-dupe consecutive identical lines.
        """
        # Context (NOT an error): normal text
        self._append_plain_line(title)
        self._append_plain_line(f"Base: {base_path}")
        if scenario_path:
            self._append_plain_line(f"Scenario: {scenario_path}")

        # Print captured validator output: only error-ish lines in red.
        body = self._sanitize_log_text(details or "").strip()
        if not body:
            self._append_error_line("(validator did not emit details)")
            return

        last = None
        for ln in body.splitlines():
            ln = self._sanitize_log_text(ln)
            if ln == last:
                continue
            last = ln
            # Same simple rule here: "ERROR" anywhere => red
            if "ERROR" in ln:
                self._append_error_line(ln)
            else:
                self._append_plain_line(ln)

    def _cleanup_thread(self):
        self.run_panel.set_running(False)
        if self._worker:
            self._worker.deleteLater()
        if self._thread:
            self._thread.deleteLater()
        self._worker = None
        self._thread = None

    def closeEvent(self, event):
        if self._thread:
            QMessageBox.warning(self, "Busy", "A run is in progress. Please wait for it to finish.")
            event.ignore()
            return
        if not self.maybe_save():
            event.ignore()
            return
        event.accept()


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
