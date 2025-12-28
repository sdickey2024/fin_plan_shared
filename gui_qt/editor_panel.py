from __future__ import annotations

import json
from typing import Any

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTabWidget, QTreeView, QPlainTextEdit, QPushButton,
    QHBoxLayout, QMessageBox, QHeaderView, QApplication, QAbstractItemDelegate
)
from PySide6.QtCore import Qt, Signal, QTimer

from .json_model import JsonModel


class EditorPanel(QWidget):
    """
    Tabbed editor:
      - Tree: QTreeView backed by JsonModel
      - Raw: QPlainTextEdit with Apply/Format
    Emits dirtyChanged when edits occur.
    """
    dirtyChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model: JsonModel | None = None
        self._resize_pending = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Tree tab
        self.tree_view = QTreeView()
        self.tree_view.setAlternatingRowColors(True)
        self.tree_view.setEditTriggers(QTreeView.DoubleClicked | QTreeView.EditKeyPressed)
        self.tree_view.setUniformRowHeights(True)
        self.tree_view.setSortingEnabled(False)

        # Make the tree usable without manual column dragging:
        # - Key column sizes to its content (but we cap it)
        # - Value column stretches to take remaining space
        hdr = self.tree_view.header()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Key
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Type (if present)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)           # Value

        # When expanding/collapsing, new/deeper keys become visible.
        # Re-fit the Key column (debounced) so it stays readable.
        self.tree_view.expanded.connect(lambda _idx: self._autosize_tree_columns_debounced())
        self.tree_view.collapsed.connect(lambda _idx: self._autosize_tree_columns_debounced())

        self.tabs.addTab(self.tree_view, "Tree")

        # Raw tab
        raw = QWidget()
        raw_layout = QVBoxLayout(raw)
        raw_layout.setContentsMargins(8, 8, 8, 8)

        btn_row = QHBoxLayout()
        self.btn_apply = QPushButton("Apply to Tree")
        self.btn_format = QPushButton("Format")
        btn_row.addWidget(self.btn_apply)
        btn_row.addWidget(self.btn_format)
        btn_row.addStretch(1)
        raw_layout.addLayout(btn_row)

        self.raw_edit = QPlainTextEdit()
        self.raw_edit.setTabStopDistance(4 * self.raw_edit.fontMetrics().horizontalAdvance(" "))
        raw_layout.addWidget(self.raw_edit)

        self.tabs.addTab(raw, "Raw JSON")

        self.btn_apply.clicked.connect(self.apply_raw)
        self.btn_format.clicked.connect(self.format_raw)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        
    def _autosize_tree_columns(self):
        """
        Resize Key column to contents, but cap it so it doesn't steal the whole view.
        Value column is set to Stretch in __init__.
        """
        try:
            self.tree_view.resizeColumnToContents(0)
            w0 = self.tree_view.columnWidth(0)
            self.tree_view.setColumnWidth(0, min(w0, 540))
        except Exception:
            pass

    def _autosize_tree_columns_debounced(self):
        """
        Debounce repeated expand/collapse signals. QTimer(0) batches resizes until
        Qt finishes layout updates for the expand/collapse.
        """
        if self._resize_pending:
            return
        self._resize_pending = True
        QTimer.singleShot(0, self._autosize_tree_columns_debounced_run)

    def _autosize_tree_columns_debounced_run(self):
        self._resize_pending = False
        self._autosize_tree_columns()

    def set_json(self, data: Any):
        self.model = JsonModel(data)
        self.tree_view.setModel(self.model)
        self.tree_view.collapseAll()
        self._autosize_tree_columns()
        self._sync_raw_from_model()
        self.model.dataChanged.connect(self._on_model_changed)

    def get_json(self) -> Any:
        if not self.model:
            return {}
        return self.model.toObject()

    def commit_pending_edits(self):
        """
        Force any active in-place editor in the tree view to commit to the model.
        Without this, clicking a menu/toolbar 'Save' can bypass the delegate's
        normal commit-on-focus-out behavior and the last edit won't be reflected
        in get_json().
        """
        try:
            tv = self.tree_view
            editor = QApplication.focusWidget()

            # Only act if the focused widget is actually an editor inside our tree view.
            if editor is not None and tv.isAncestorOf(editor):
                # Push editor contents into the model
                tv.commitData(editor)
                # Close editor and submit any cached value
                tv.closeEditor(editor, QAbstractItemDelegate.SubmitModelCache)

            # Ensure any queued signals/edits are processed before reading JSON
            QApplication.processEvents()
        except Exception:
            pass

    def is_dirty(self) -> bool:
        return bool(self.model and self.model.isDirty())

    def set_clean(self):
        if self.model:
            self.model.setClean()
            self.dirtyChanged.emit(False)

    def _on_model_changed(self, *_):
        if self.model and self.model.isDirty():
            self.dirtyChanged.emit(True)

    def _on_tab_changed(self, idx: int):
        # When entering Raw tab, refresh from model (unless raw has unsaved edits;
        # we intentionally treat Raw as a view unless Apply is used.)
        if idx == 1:
            self._sync_raw_from_model()

    def _sync_raw_from_model(self):
        if not self.model:
            return
        txt = json.dumps(self.model.toObject(), indent=4)
        self.raw_edit.blockSignals(True)
        self.raw_edit.setPlainText(txt)
        self.raw_edit.blockSignals(False)

    def apply_raw(self):
        txt = self.raw_edit.toPlainText().strip()
        if not txt:
            return
        try:
            data = json.loads(txt)
        except Exception as e:
            QMessageBox.critical(self, "Invalid JSON", str(e))
            return
        if not self.model:
            self.set_json(data)
        else:
            self.model.resetData(data)
            self._autosize_tree_columns()
            self.dirtyChanged.emit(True)

    def format_raw(self):
        txt = self.raw_edit.toPlainText().strip()
        if not txt:
            return
        try:
            data = json.loads(txt)
        except Exception as e:
            QMessageBox.critical(self, "Invalid JSON", str(e))
            return
        self.raw_edit.setPlainText(json.dumps(data, indent=4))
