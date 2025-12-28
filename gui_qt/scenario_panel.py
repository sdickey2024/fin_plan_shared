from __future__ import annotations

import os
import json
from dataclasses import dataclass
from typing import List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QHBoxLayout, QCheckBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontMetrics

class SelectAllCheckBox(QCheckBox):
    """
    A tri-state checkbox that *displays* PartiallyChecked, but never cycles into
    PartiallyChecked due to user clicks.
    User toggles only: Unchecked <-> Checked.
    PartiallyChecked is reserved for programmatic display when the selection is mixed.
    """
    def nextCheckState(self):
        st = self.checkState()
        if st == Qt.Unchecked:
            self.setCheckState(Qt.Checked)
        else:
            # Treat PartiallyChecked the same as Checked for user toggling.
            self.setCheckState(Qt.Unchecked)

@dataclass
class ScenarioInfo:
    path: str
    description: str
    life_events_count: int
    has_assumptions: bool
    valid: bool
    error: str = ""

SCHEMA_TYPE_FIELD = "schema_type"
SCHEMA_TYPE_SCENARIO = "scenario"

class ScenarioPanel(QWidget):
    selectionChanged = Signal()
    openRequested = Signal(str)
    preferredWidthChanged = Signal(int)

    def __init__(self, data_dir: str, parent=None):
        super().__init__(parent)
        self.data_dir = data_dir
        self.base_path: Optional[str] = None
        self._bulk_selecting = False

        # enable this to report debug in the below checkbox/scenario options
        self._dbg = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        layout.addWidget(QLabel("Scenarios"))
        # Header row: label + "select all" checkbox
        header = QHBoxLayout()
        header.addWidget(QLabel("Scenarios: Select All"), 0)
        self.chk_select_all = SelectAllCheckBox()
        self.chk_select_all.setTristate(True)
        self.chk_select_all.setCheckState(Qt.Unchecked)
        self.chk_select_all.stateChanged.connect(self._on_select_all_state_changed)
        header.addWidget(self.chk_select_all, 0)
        header.addStretch(1)
        layout.addLayout(header)

        self.list = QListWidget()
        # Even if we cap the left pane width, keep the list readable.
        self.list.setTextElideMode(Qt.ElideRight)
        self.list.itemChanged.connect(lambda *_: self.selectionChanged.emit())
        self.list.itemChanged.connect(self._on_item_changed)
        self.list.itemDoubleClicked.connect(self._open_item)
        layout.addWidget(self.list, 1)

        btns = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh")
        btns.addWidget(self.btn_refresh)
        btns.addStretch(1)
        layout.addLayout(btns)

        self.btn_refresh.clicked.connect(self.refresh)

    def _dbg_print(self, *args):
        if self._dbg:
            print("[ScenarioPanel]", *args)

    def _cs(self, st) -> int:
        """
        Convert Qt.CheckState to a stable integer 0/1/2.
        PySide6 may return a CheckState enum that doesn't support int(st).
        """
        try:
            return int(st.value)  # Qt.CheckState enum
        except Exception:
            return int(st)

    def _dump_items(self, prefix: str, limit: int = 8):
        """Dump first N items' label + check state for debugging."""
        try:
            n = self.list.count()
        except Exception as e:
            self._dbg_print(prefix, "count() failed:", repr(e))
            return
        self._dbg_print(prefix, "count =", n)
        for i in range(min(n, limit)):
            it = self.list.item(i)
            if it is None:
                self._dbg_print(prefix, f"  [{i}] item=None")
                continue
            label = it.text()
            st = it.checkState()
            self._dbg_print(prefix, f"  [{i}] state={self._cs(st)} text={label!r}")
        
    def _open_item(self, item: QListWidgetItem):
        path = item.data(Qt.UserRole)
        if path:
            self.openRequested.emit(path)

    def set_base_path(self, base_path: Optional[str]):
        self.base_path = base_path
        self.refresh()

    def refresh(self):
        self._dbg_print("refresh() begin; base_path =", self.base_path)
        self.list.blockSignals(True)
        self.list.clear()

        if not os.path.isdir(self.data_dir):
            self.list.blockSignals(False)
            self._dbg_print("refresh() end early: data_dir missing:", self.data_dir)
            self._update_select_all_state()
            return

        for fname in sorted(os.listdir(self.data_dir)):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(self.data_dir, fname)
            if self.base_path and os.path.abspath(path) == os.path.abspath(self.base_path):
                continue
            # No heuristics: a scenario file MUST explicitly declare
            #   { "schema_type": "scenario" }
            # Files without this are not treated as scenarios and are not listed.
            info = self._read_scenario_info(path)
            if not info:
                continue

            label = os.path.basename(path)
            if info.description:
                label += f" — {info.description}"
            if not info.valid:
                label += " [INVALID]"

            item = QListWidgetItem(label)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            tooltip = (
                f"File: {os.path.basename(path)}\n"
                f"{SCHEMA_TYPE_FIELD}: {SCHEMA_TYPE_SCENARIO}\n"
                f"Valid: {'yes' if info.valid else 'no'}\n"
                f"Description: {info.description}\n"
                f"Life events: {info.life_events_count}\n"
                f"Has assumptions override: {'yes' if info.has_assumptions else 'no'}"
            )
            if not info.valid and info.error:
                tooltip += f"\nError: {info.error}"
            item.setToolTip(tooltip)
            item.setData(Qt.UserRole, info.path)
            self.list.addItem(item)

        self.list.blockSignals(False)
        self._dump_items("refresh() after populate")
        self._update_select_all_state()
        self.selectionChanged.emit()
        self._dbg_print("refresh() end")

        # Suggest a better width for the scenario pane, so users can read labels
        # without manually dragging the splitter every run.
        #
        # We clamp so one monster description doesn't steal the whole window.
        try:
            fm = QFontMetrics(self.list.font())
            widest = 0
            for i in range(self.list.count()):
                it = self.list.item(i)
                if not it:
                    continue
                widest = max(widest, fm.horizontalAdvance(it.text()))

            # padding accounts for checkbox, margins, and potential scrollbar
            padding = 90
            preferred = widest + padding
            preferred = max(420, min(preferred, 820))
            self.preferredWidthChanged.emit(int(preferred))
        except Exception:
            # never let heuristics break refresh()
            pass

    def selected_scenarios(self) -> List[str]:
        out = []
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.checkState() == Qt.Checked:
                out.append(item.data(Qt.UserRole))
        return out

    def _on_item_changed(self, *_):
        # Avoid recursion during bulk operations
        if self._bulk_selecting:
            return
        # Minimal debug: show select-all state changes driven by manual item changes
        self._dbg_print("_on_item_changed: updating select-all derived state")
        self._update_select_all_state()
        self.selectionChanged.emit()

    def _on_select_all_state_changed(self, state: int):
        self._dbg_print("_on_select_all_state_changed state =", self._cs(state))
        self._dump_items("before bulk")

        # Avoid recursion during bulk operations
        if self._bulk_selecting:
            self._dbg_print("  ignoring: _bulk_selecting is True")
            return

        self._bulk_selecting = True
        try:
            # IMPORTANT:
            # PySide6 may pass a Qt.CheckState enum instance whose equality/membership
            # checks do not behave reliably against Qt.Checked/Qt.PartiallyChecked.
            # Use the numeric value instead.
            s = self._cs(state)  # 0=Unchecked, 1=PartiallyChecked, 2=Checked
            target = Qt.Checked if s != 0 else Qt.Unchecked
            self._dbg_print("  computed target =", self._cs(target), "(2=Checked,0=Unchecked) from state", s)

            self._dbg_print("  list.count() =", self.list.count())
            self._dbg_print("  list.blockSignals() =", self.list.signalsBlocked())

            # IMPORTANT: do not block list signals here. Some Qt/PySide6 paths
            # fail to visually update check states when signals are blocked.
            # _bulk_selecting prevents recursion/noise.
            for i in range(self.list.count()):
                item = self.list.item(i)
                if item is not None:
                    prev = self._cs(item.checkState())
                    item.setCheckState(target)
                    now = self._cs(item.checkState())
                    if i < 8:
                        self._dbg_print(f"  item[{i}] {prev} -> {now}")
                else:
                    self._dbg_print("  item[", i, "] is None")

            self._dump_items("after bulk")
            self._update_select_all_state()
            self.selectionChanged.emit()
        finally:
            self._bulk_selecting = False

    def _update_select_all_state(self):
        total = self.list.count()
        # Debug: derived select-all display state
        self._dbg_print("_update_select_all_state total =", total)
        if total == 0:
            st = Qt.Unchecked
        else:
            checked = 0
            for i in range(total):
                if self.list.item(i).checkState() == Qt.Checked:
                    checked += 1
            if checked == 0:
                st = Qt.Unchecked
            elif checked == total:
                st = Qt.Checked
            else:
                st = Qt.PartiallyChecked

        self.chk_select_all.blockSignals(True)
        self.chk_select_all.setCheckState(st)
        self.chk_select_all.blockSignals(False)
        self._dbg_print("_update_select_all_state ->", self._cs(st), "(0/1/2)")

    def _read_scenario_info(self, path: str) -> Optional[ScenarioInfo]:
        try:
            with open(path, "r") as f:
                j = json.load(f)
            if not isinstance(j, dict):
                return None

            # No guessing: schema_type must explicitly declare it is a scenario.
            if j.get(SCHEMA_TYPE_FIELD) != SCHEMA_TYPE_SCENARIO:
                return None

            desc = str(j.get("description", "")) if "description" in j else ""
            le = j.get("life_events", [])
            le_count = len(le) if isinstance(le, list) else 0
            has_assump = isinstance(j.get("assumptions", None), dict)

            # Validate required fields for display/debug labeling.
            # This does NOT affect classification (schema_type does that).
            valid = True
            err = ""
            if "description" not in j:
                valid = False
                err = "Missing required top-level field 'description'"
            elif "life_events" not in j:
                valid = False
                err = "Missing required top-level field 'life_events'"
            elif not isinstance(j.get("life_events"), list):
                valid = False
                err = "'life_events' must be a list"

            return ScenarioInfo(
                path=path,
                description=desc,
                life_events_count=le_count,
                has_assumptions=has_assump,
                valid=valid,
                error=err,
            )

        except Exception:
            return None
