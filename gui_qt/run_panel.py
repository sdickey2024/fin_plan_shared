from __future__ import annotations

import traceback
from typing import List, Optional
import subprocess

from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QComboBox
import os
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QComboBox, QSpinBox
from PySide6.QtCore import QObject, QThread, Signal


class RunWorker(QObject):
    progress = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, cmd: List[str], cwd: Optional[str] = None):
        super().__init__()
        self.cmd = cmd
        self.cwd = cwd

    def run(self):
        import os
        os.environ["MPLBACKEND"] = "Agg"
        import matplotlib
        matplotlib.use("Agg", force=True)

        try:
            self.progress.emit("Launching CLI:")
            self.progress.emit("  " + " ".join(self.cmd))

            proc = subprocess.Popen(
                self.cmd,
                cwd=self.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            assert proc.stdout is not None
            for line in proc.stdout:
                self.progress.emit(line.rstrip("\n"))

            rc = proc.wait()
            if rc == 0:
                self.finished.emit(True, "")
            else:
                self.finished.emit(False, f"CLI exited with code {rc}")
        except Exception as e:
            tb = traceback.format_exc()
            self.finished.emit(False, f"{e}\n\n{tb}")


class RunPanel(QWidget):
    runRequested = Signal()
    openGraphsRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        self.btn_run = QPushButton("Run Selected Scenarios")
        layout.addWidget(self.btn_run)

        self.btn_open_graphs = QPushButton("Open Graphs")
        layout.addWidget(self.btn_open_graphs)

        layout.addWidget(QLabel("Jobs"))
        self.spin_jobs = QSpinBox()
        self.spin_jobs.setRange(1, 64)
        cpu = os.cpu_count() or 8
        self.spin_jobs.setValue(min(8, cpu))
        self.spin_jobs.setFixedWidth(70)
        layout.addWidget(self.spin_jobs)

        layout.addWidget(QLabel("Granularity"))
        self.cmb_gran = QComboBox()
        self.cmb_gran.addItems(["monthly", "yearly"])
        layout.addWidget(self.cmb_gran)

        layout.addWidget(QLabel("Mode"))
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems(["events", "mc"])
        # "events" = deterministic/event-driven, "mc" = montecarlo force
        self.cmb_mode.addItems(["events", "mc"])
        layout.addWidget(self.cmb_mode)

        self.status = QLabel("")
        self.status.setStyleSheet("color: gray;")
        layout.addWidget(self.status, 1)

        self.btn_run.clicked.connect(self.runRequested.emit)
        self.btn_open_graphs.clicked.connect(self.openGraphsRequested.emit)

    def granularity(self) -> str:
        return self.cmb_gran.currentText()

    def montecarlo_mode(self) -> str:
        return self.cmb_mode.currentText()

    def jobs(self) -> int:
        return int(self.spin_jobs.value())

    def set_status(self, text: str):
        self.status.setText(text)

    def set_running(self, running: bool):
        self.btn_run.setEnabled(not running)
        self.spin_jobs.setEnabled(not running)
