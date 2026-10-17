# Arduino Telemetry Visualizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python desktop app that visualizes Arduino telemetry (TEMP/ALT/BARO/PITCH/ROLL/ACCXYZ/GYRXYZ) either live over serial or replayed from an SD-card log file, with scrolling line graphs and a pitch/roll attitude indicator.

**Architecture:** A single PySide6 `MainWindow` is fed `Sample` objects from one of two interchangeable sources — a background-thread `SerialReader` for live serial, or a `QTimer`-driven `LogPlayer` for file replay — both built on a shared, pure `parse_line` function that structurally classifies pipe-delimited data lines vs. arbitrary boot/calibration text.

**Tech Stack:** Python 3.10+, PySide6, pyqtgraph, pyserial, pytest.

**Spec:** `docs/superpowers/specs/2026-08-22-arduino-telemetry-visualizer-design.md`

## Global Constraints

- Python 3.10+, Windows target (COM ports via pyserial).
- Package root is `arduino_viz/`; run the app from the project root with `python -m arduino_viz.main`.
- Core deps: `PySide6`, `pyqtgraph`, `pyserial`. Dev/test dep: `pytest`.
- `log_format.py` is pure (no Qt/IO) and gets full pytest coverage. Serial I/O, QTimer-driven playback timing, and GUI rendering are verified manually, per the spec — do not force brittle Qt-event-loop unit tests onto them.
- Data-line detection is structural (exactly 12 `|`-delimited numeric fields), never string-matching specific boot messages.
- The `HH:MM:SS.mmm -> ` IDE timestamp prefix is stripped if present but never required.

---

### Task 1: Project scaffolding & dependencies

**Files:**
- Create: `requirements.txt`
- Create: `arduino_viz/__init__.py`
- Create: `.gitignore`
- Create: `pytest.ini`

**Interfaces:**
- Consumes: nothing.
- Produces: an installable, importable `arduino_viz` package; a working `pytest` invocation from the project root.

- [ ] **Step 1: Create `requirements.txt`**

```
PySide6>=6.5
pyqtgraph>=0.13
pyserial>=3.5
pytest>=7.0
```

- [ ] **Step 2: Create `arduino_viz/__init__.py`**

```python
```

(empty file — marks `arduino_viz` as a package)

- [ ] **Step 3: Create `.gitignore`**

```
__pycache__/
*.pyc
.venv/
venv/
.idea/
*.egg-info/
```

- [ ] **Step 4: Create `pytest.ini`**

```ini
[pytest]
pythonpath = .
```

This guarantees `import arduino_viz...` works in tests regardless of how `pytest` is invoked.

- [ ] **Step 5: Install dependencies and verify imports**

Run: `pip install -r requirements.txt`
Then run: `python -c "import PySide6, pyqtgraph, serial, pytest; print('ok')"`
Expected: prints `ok` with no errors.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt arduino_viz/__init__.py .gitignore pytest.ini
git commit -m "chore: scaffold arduino_viz project"
```

---

### Task 2: Log line parser

**Files:**
- Create: `arduino_viz/log_format.py`
- Test: `tests/test_log_format.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Sample` dataclass with fields `time_ms: int, temp_c: float, alt_m: float, baro_hpa: float, pitch: float, roll: float, accx: float, accy: float, accz: float, gyrx: float, gyry: float, gyrz: float`, and `parse_line(line: str) -> Optional[Sample]` in `arduino_viz.log_format`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_log_format.py`:

```python
from arduino_viz.log_format import parse_line, Sample


def test_parses_valid_data_line():
    line = "000002 | 0080 | 0000 | 1015 | 0.003 | -0.000 | 0.0027 | 0.0263 | 0.9996 | 0.0762 | 0.0152 | -0.0915"
    assert parse_line(line) == Sample(
        time_ms=2, temp_c=8.0, alt_m=0.0, baro_hpa=1015.0,
        pitch=0.003, roll=-0.0, accx=0.0027, accy=0.0263, accz=0.9996,
        gyrx=0.0762, gyry=0.0152, gyrz=-0.0915,
    )


def test_strips_ide_timestamp_prefix():
    line = "20:55:50.470 -> 000002 | 0080 | 0000 | 1015 | 0.003 | -0.000 | 0.0027 | 0.0263 | 0.9996 | 0.0762 | 0.0152 | -0.0915"
    assert parse_line(line) is not None


def test_negative_values_line():
    line = "000003 | 0080 | 0000 | 1015 | 0.005 | -0.004 | 0.0008 | 0.0269 | 0.9996 | -0.0152 | -0.0610 | -0.0457"
    sample = parse_line(line)
    assert sample.roll == -0.004
    assert sample.gyrz == -0.0457


def test_rejects_column_header_line():
    line = "  TIME  | TEMP |  ALT | BARO | PITCH | ROLL  |  ACCX  |  ACCY  |  ACCZ  |  GYRX  |  GYRY  |  GYRZ"
    assert parse_line(line) is None


def test_rejects_blank_line():
    assert parse_line("") is None
    assert parse_line("   ") is None


def test_rejects_calibration_progress_line():
    line = ">*****..........>..........These are the Active offsets: "
    assert parse_line(line) is None


def test_rejects_comma_separated_offsets_line():
    line = "-3434.00000,    -2011.00000,    4028.00000,    344.00000,    55.00000,    -13.00000"
    assert parse_line(line) is None


def test_rejects_status_text_lines():
    for line in ("Chip ID: 0x58", "BMP280 Online", "MPU1 Online",
                 "System check complete. Logging started."):
        assert parse_line(line) is None


def test_rejects_malformed_data_line_wrong_field_count():
    line = "000002 | 0080 | 0000 | 1015 | 0.003 | -0.000 | 0.0027 | 0.0263 | 0.9996 | 0.0762 | 0.0152"
    assert parse_line(line) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_log_format.py -v`
Expected: FAIL/ERROR — `arduino_viz.log_format` doesn't exist yet.

- [ ] **Step 3: Implement `arduino_viz/log_format.py`**

```python
import re
from dataclasses import dataclass
from typing import Optional

_TIMESTAMP_PREFIX = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3}\s*->\s*")
_FIELD_COUNT = 12


@dataclass
class Sample:
    time_ms: int
    temp_c: float
    alt_m: float
    baro_hpa: float
    pitch: float
    roll: float
    accx: float
    accy: float
    accz: float
    gyrx: float
    gyry: float
    gyrz: float


def parse_line(line: str) -> Optional[Sample]:
    """Parse one line of the board's log format into a Sample.

    Returns None for anything that isn't a full 12-field numeric data
    line (header line, blank line, boot/calibration text) rather than
    raising, since the boot sequence is arbitrary free text with no
    fixed set of messages to match against.
    """
    stripped = _TIMESTAMP_PREFIX.sub("", line).strip()
    if not stripped:
        return None

    fields = [f.strip() for f in stripped.split("|")]
    if len(fields) != _FIELD_COUNT:
        return None

    try:
        values = [float(f) for f in fields]
    except ValueError:
        return None

    (time_raw, temp_raw, alt_raw, baro_raw, pitch, roll,
     accx, accy, accz, gyrx, gyry, gyrz) = values

    return Sample(
        time_ms=int(time_raw),
        temp_c=temp_raw / 10.0,
        alt_m=alt_raw,
        baro_hpa=baro_raw,
        pitch=pitch,
        roll=roll,
        accx=accx,
        accy=accy,
        accz=accz,
        gyrx=gyrx,
        gyry=gyry,
        gyrz=gyrz,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_log_format.py -v`
Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add arduino_viz/log_format.py tests/test_log_format.py
git commit -m "feat: add structural log line parser"
```

---

### Task 3: File-based log source

**Files:**
- Create: `arduino_viz/file_source.py`
- Test: `tests/test_file_source.py`

**Interfaces:**
- Consumes: `Sample`, `parse_line` from `arduino_viz.log_format`.
- Produces: `LogFileFormatError(Exception)`; `load_log_file(path: str) -> list[Sample]`; `LogPlayer(QObject)` — constructor `LogPlayer(samples: list[Sample], parent=None)`, signals `sample_ready(int, object)` (index, `Sample`) and `finished()`, methods `play()`, `pause()`, `seek(index: int)`, `set_speed(speed: float)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_file_source.py`:

```python
import pytest

from arduino_viz.file_source import LogFileFormatError, load_log_file, _delay_ms
from arduino_viz.log_format import Sample


def _sample(time_ms):
    return Sample(
        time_ms=time_ms, temp_c=0, alt_m=0, baro_hpa=0, pitch=0, roll=0,
        accx=0, accy=0, accz=0, gyrx=0, gyry=0, gyrz=0,
    )


def test_load_log_file_returns_samples(tmp_path):
    content = (
        "Initializing Pins\n"
        "BMP280 Online\n"
        "System check complete. Logging started.\n"
        "  TIME  | TEMP |  ALT | BARO | PITCH | ROLL  |  ACCX  |  ACCY  |  ACCZ  |  GYRX  |  GYRY  |  GYRZ\n"
        "000002 | 0080 | 0000 | 1015 | 0.003 | -0.000 | 0.0027 | 0.0263 | 0.9996 | 0.0762 | 0.0152 | -0.0915\n"
        "000003 | 0080 | 0000 | 1015 | 0.005 | -0.004 | 0.0008 | 0.0269 | 0.9996 | -0.0152 | -0.0610 | -0.0457\n"
    )
    log_file = tmp_path / "sample.txt"
    log_file.write_text(content, encoding="utf-8")

    samples = load_log_file(str(log_file))

    assert len(samples) == 2
    assert samples[0].time_ms == 2
    assert samples[1].gyrz == -0.0457


def test_load_log_file_raises_on_no_data_lines(tmp_path):
    log_file = tmp_path / "empty.txt"
    log_file.write_text("Initializing Pins\nBMP280 Online\n", encoding="utf-8")

    with pytest.raises(LogFileFormatError):
        load_log_file(str(log_file))


def test_delay_ms_scales_with_speed():
    a, b = _sample(100), _sample(300)
    assert _delay_ms(a, b, 1.0) == 200
    assert _delay_ms(a, b, 2.0) == 100


def test_delay_ms_never_negative():
    a, b = _sample(300), _sample(100)
    assert _delay_ms(a, b, 1.0) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_file_source.py -v`
Expected: FAIL/ERROR — `arduino_viz.file_source` doesn't exist yet.

- [ ] **Step 3: Implement `arduino_viz/file_source.py`**

```python
from PySide6.QtCore import QObject, QTimer, Signal

from .log_format import Sample, parse_line


class LogFileFormatError(Exception):
    pass


def load_log_file(path: str) -> list[Sample]:
    samples: list[Sample] = []
    first_line = None
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw_line in f:
            stripped = raw_line.strip()
            if first_line is None and stripped:
                first_line = stripped
            sample = parse_line(raw_line)
            if sample is not None:
                samples.append(sample)

    if not samples:
        raise LogFileFormatError(
            f"No valid data lines found in file. First line: {first_line!r}"
        )
    return samples


def _delay_ms(prev: Sample, next_: Sample, speed: float) -> int:
    delta = next_.time_ms - prev.time_ms
    return max(0, int(delta / speed))


class LogPlayer(QObject):
    sample_ready = Signal(int, object)  # index, Sample
    finished = Signal()

    def __init__(self, samples: list[Sample], parent=None):
        super().__init__(parent)
        self._samples = samples
        self._index = 0
        self._speed = 1.0
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._emit_next)

    def play(self) -> None:
        if self._index < len(self._samples):
            self._timer.start(0)

    def pause(self) -> None:
        self._timer.stop()

    def seek(self, index: int) -> None:
        self._timer.stop()
        self._index = max(0, min(index, len(self._samples)))

    def set_speed(self, speed: float) -> None:
        self._speed = max(speed, 0.01)

    def _emit_next(self) -> None:
        if self._index >= len(self._samples):
            self.finished.emit()
            return

        index = self._index
        sample = self._samples[index]
        self.sample_ready.emit(index, sample)
        self._index += 1

        if self._index < len(self._samples):
            delay = _delay_ms(sample, self._samples[self._index], self._speed)
            self._timer.start(delay)
        else:
            self.finished.emit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_file_source.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add arduino_viz/file_source.py tests/test_file_source.py
git commit -m "feat: add log file loading and timed playback"
```

---

### Task 4: Serial data source

**Files:**
- Create: `arduino_viz/serial_source.py`

**Interfaces:**
- Consumes: `Sample`, `parse_line` from `arduino_viz.log_format`.
- Produces: `list_serial_ports() -> list[str]`; `SerialReader(QThread)` — constructor `SerialReader(port: str, baud: int, parent=None)`, signals `sample_received(object)` (`Sample`), `boot_line(str)`, `skipped_line()`, `error(str)`, method `stop()`.

- [ ] **Step 1: Implement `arduino_viz/serial_source.py`**

No automated tests for this file — it talks to real hardware, and per the spec, serial I/O is verified manually (Task 7's manual test covers it end-to-end).

```python
import serial
from PySide6.QtCore import QThread, Signal
from serial.tools import list_ports

from .log_format import parse_line


def list_serial_ports() -> list[str]:
    return [p.device for p in list_ports.comports()]


class SerialReader(QThread):
    sample_received = Signal(object)  # Sample
    boot_line = Signal(str)
    skipped_line = Signal()
    error = Signal(str)

    def __init__(self, port: str, baud: int, parent=None):
        super().__init__(parent)
        self._port = port
        self._baud = baud
        self._running = False

    def run(self) -> None:
        self._running = True
        seen_first_sample = False
        try:
            with serial.Serial(self._port, self._baud, timeout=1) as ser:
                while self._running:
                    raw = ser.readline()
                    if not raw:
                        continue
                    try:
                        line = raw.decode("utf-8", errors="replace")
                    except Exception:
                        continue

                    sample = parse_line(line)
                    if sample is not None:
                        seen_first_sample = True
                        self.sample_received.emit(sample)
                    elif not seen_first_sample:
                        stripped = line.strip()
                        if stripped:
                            self.boot_line.emit(stripped)
                    else:
                        self.skipped_line.emit()
        except serial.SerialException as exc:
            self.error.emit(str(exc))
        finally:
            self._running = False

    def stop(self) -> None:
        self._running = False
        self.wait(2000)
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `python -c "from arduino_viz.serial_source import SerialReader, list_serial_ports; print(list_serial_ports())"`
Expected: prints a list (possibly empty if no board plugged in), no errors.

- [ ] **Step 3: Commit**

```bash
git add arduino_viz/serial_source.py
git commit -m "feat: add threaded serial reader with boot-line detection"
```

---

### Task 5: Attitude indicator widget

**Files:**
- Create: `arduino_viz/attitude_widget.py`
- Create: `scripts/preview_attitude.py`

**Interfaces:**
- Consumes: nothing beyond PySide6.
- Produces: `AttitudeIndicator(QWidget)` with `set_orientation(pitch: float, roll: float) -> None` (radians).

- [ ] **Step 1: Implement `arduino_viz/attitude_widget.py`**

```python
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget


class AttitudeIndicator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pitch = 0.0  # radians
        self._roll = 0.0  # radians
        self.setMinimumSize(150, 150)

    def set_orientation(self, pitch: float, roll: float) -> None:
        self._pitch = pitch
        self._roll = roll
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height())
        painter.translate(self.width() / 2, self.height() / 2)

        pitch_deg = math.degrees(self._pitch)
        roll_deg = math.degrees(self._roll)
        pixels_per_degree = side / 90.0

        painter.save()
        painter.rotate(-roll_deg)
        painter.translate(0, pitch_deg * pixels_per_degree)

        half = side * 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(60, 120, 200)))
        painter.drawRect(QRectF(-half, -half, 2 * half, half))
        painter.setBrush(QBrush(QColor(120, 80, 40)))
        painter.drawRect(QRectF(-half, 0, 2 * half, half))

        painter.setPen(QPen(Qt.white, 2))
        painter.drawLine(QPointF(-half, 0), QPointF(half, 0))
        painter.restore()

        painter.setPen(QPen(Qt.yellow, 3))
        painter.drawLine(QPointF(-side * 0.25, 0), QPointF(-side * 0.08, 0))
        painter.drawLine(QPointF(side * 0.08, 0), QPointF(side * 0.25, 0))
        painter.drawEllipse(QPointF(0, 0), 3, 3)
```

- [ ] **Step 2: Create a manual preview script — `scripts/preview_attitude.py`**

```python
import math
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QSlider, QVBoxLayout, QWidget

sys.path.insert(0, ".")
from arduino_viz.attitude_widget import AttitudeIndicator


class PreviewWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Attitude Indicator Preview")
        self.indicator = AttitudeIndicator()
        self.pitch_slider = QSlider(Qt.Horizontal)
        self.pitch_slider.setRange(-90, 90)
        self.roll_slider = QSlider(Qt.Horizontal)
        self.roll_slider.setRange(-180, 180)
        self.pitch_slider.valueChanged.connect(self._update)
        self.roll_slider.valueChanged.connect(self._update)

        layout = QVBoxLayout(self)
        layout.addWidget(self.indicator)
        layout.addWidget(QLabel("Pitch"))
        layout.addWidget(self.pitch_slider)
        layout.addWidget(QLabel("Roll"))
        layout.addWidget(self.roll_slider)

    def _update(self) -> None:
        pitch = math.radians(self.pitch_slider.value())
        roll = math.radians(self.roll_slider.value())
        self.indicator.set_orientation(pitch, roll)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PreviewWindow()
    window.resize(300, 400)
    window.show()
    sys.exit(app.exec())
```

- [ ] **Step 3: Manually verify**

Run: `python scripts/preview_attitude.py`
Expected: a window opens with a sky/ground horizon and a yellow aircraft symbol; dragging the Pitch slider moves the horizon up/down, dragging the Roll slider rotates it. Close the window when satisfied.

- [ ] **Step 4: Commit**

```bash
git add arduino_viz/attitude_widget.py scripts/preview_attitude.py
git commit -m "feat: add QPainter attitude indicator widget"
```

---

### Task 6: Main window skeleton (plots, attitude, readout)

**Files:**
- Create: `arduino_viz/main_window.py`
- Create: `arduino_viz/main.py`
- Create: `scripts/preview_main_window.py`

**Interfaces:**
- Consumes: `Sample` from `arduino_viz.log_format`; `AttitudeIndicator` from `arduino_viz.attitude_widget`.
- Produces: `MainWindow(QMainWindow)` with slots `on_sample(sample: Sample) -> None`, `on_boot_line(text: str) -> None`, `on_skipped_line() -> None`; module-level `main() -> None` entry point in `arduino_viz.main`.

- [ ] **Step 1: Implement `arduino_viz/main_window.py`**

```python
from collections import deque

import pyqtgraph as pg
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .attitude_widget import AttitudeIndicator
from .log_format import Sample

BUFFER_LEN = 2000


class ChannelGroupPlot(pg.PlotWidget):
    def __init__(self, channel_names: list[str], colors: list[str], title: str, parent=None):
        super().__init__(parent)
        self.setTitle(title)
        self.addLegend()
        self._time = deque(maxlen=BUFFER_LEN)
        self._channels = {name: deque(maxlen=BUFFER_LEN) for name in channel_names}
        self._curves = {
            name: self.plot([], [], pen=color, name=name)
            for name, color in zip(channel_names, colors)
        }

    def append(self, time_ms: int, values: dict) -> None:
        self._time.append(time_ms)
        for name, curve in self._curves.items():
            self._channels[name].append(values[name])
            curve.setData(list(self._time), list(self._channels[name]))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Arduino Telemetry Visualizer")

        self.env_plot = ChannelGroupPlot(
            ["temp_c", "alt_m", "baro_hpa"], ["r", "g", "b"],
            "Environment (TEMP degC / ALT m / BARO hPa)",
        )
        self.accel_plot = ChannelGroupPlot(
            ["accx", "accy", "accz"], ["r", "g", "b"], "Accelerometer (g)",
        )
        self.gyro_plot = ChannelGroupPlot(
            ["gyrx", "gyry", "gyrz"], ["r", "g", "b"], "Gyroscope (rad/s)",
        )

        tabs = QTabWidget()
        tabs.addTab(self.env_plot, "Environment")
        tabs.addTab(self.accel_plot, "Accelerometer")
        tabs.addTab(self.gyro_plot, "Gyroscope")

        self.attitude = AttitudeIndicator()
        self.readout_labels: dict[str, QLabel] = {}
        readout_form = QFormLayout()
        for field in Sample.__dataclass_fields__:
            label = QLabel("--")
            self.readout_labels[field] = label
            readout_form.addRow(field, label)

        side_panel = QWidget()
        side_layout = QVBoxLayout(side_panel)
        side_layout.addWidget(self.attitude)
        side_layout.addLayout(readout_form)

        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.addWidget(tabs, stretch=3)
        content_layout.addWidget(side_panel, stretch=1)
        self.setCentralWidget(content)

        self._skipped_count = 0
        self._logging_started = False
        self.statusBar().showMessage("Not connected")

    def on_sample(self, sample: Sample) -> None:
        self._logging_started = True
        self.env_plot.append(sample.time_ms, {
            "temp_c": sample.temp_c, "alt_m": sample.alt_m, "baro_hpa": sample.baro_hpa,
        })
        self.accel_plot.append(sample.time_ms, {
            "accx": sample.accx, "accy": sample.accy, "accz": sample.accz,
        })
        self.gyro_plot.append(sample.time_ms, {
            "gyrx": sample.gyrx, "gyry": sample.gyry, "gyrz": sample.gyrz,
        })
        self.attitude.set_orientation(sample.pitch, sample.roll)
        for field, label in self.readout_labels.items():
            value = getattr(sample, field)
            label.setText(f"{value:.4f}" if isinstance(value, float) else str(value))
        self.statusBar().showMessage(f"Logging — {self._skipped_count} skipped lines")

    def on_boot_line(self, text: str) -> None:
        if not self._logging_started:
            self.statusBar().showMessage(text)

    def on_skipped_line(self) -> None:
        self._skipped_count += 1
```

- [ ] **Step 2: Implement `arduino_viz/main.py`**

```python
import sys

from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(1000, 650)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Create a manual preview script — `scripts/preview_main_window.py`**

Feeds synthetic samples into the window on a timer, so the plotting/attitude/readout skeleton can be checked before wiring real data sources.

```python
import math
import sys

sys.path.insert(0, ".")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from arduino_viz.log_format import Sample
from arduino_viz.main_window import MainWindow

app = QApplication(sys.argv)
win = MainWindow()
win.resize(1000, 650)
win.show()

state = {"i": 0}


def tick():
    i = state["i"]
    sample = Sample(
        time_ms=i * 100, temp_c=8.0 + 0.01 * i, alt_m=0.0, baro_hpa=1015.0,
        pitch=math.sin(i / 20), roll=math.cos(i / 15),
        accx=0.01 * math.sin(i / 5), accy=0.01 * math.cos(i / 5), accz=0.9996,
        gyrx=0.05 * math.sin(i / 3), gyry=0.02, gyrz=-0.09,
    )
    win.on_sample(sample)
    state["i"] += 1


timer = QTimer()
timer.timeout.connect(tick)
timer.start(50)

sys.exit(app.exec())
```

- [ ] **Step 4: Manually verify**

Run: `python scripts/preview_main_window.py`
Expected: window opens with three tabs (Environment/Accelerometer/Gyroscope) whose plots scroll continuously; the attitude indicator on the right rocks back and forth; the numeric readout table updates every tick; status bar reads "Logging — 0 skipped lines". Close the window when satisfied.

- [ ] **Step 5: Commit**

```bash
git add arduino_viz/main_window.py arduino_viz/main.py scripts/preview_main_window.py
git commit -m "feat: add main window with scrolling plots and attitude readout"
```

---

### Task 7: Live serial wiring

**Files:**
- Modify: `arduino_viz/main_window.py`

**Interfaces:**
- Consumes: `SerialReader`, `list_serial_ports` from `arduino_viz.serial_source`; `MainWindow.on_sample`, `on_boot_line`, `on_skipped_line` from Task 6.
- Produces: `MainWindow.serial_controls` (QWidget), methods `refresh_ports()`, `toggle_serial_connection()`, `connect_serial()`, `disconnect_serial()`, `on_serial_error(message: str)`.

- [ ] **Step 1: Add imports**

In `arduino_viz/main_window.py`, find:

```python
from .attitude_widget import AttitudeIndicator
from .log_format import Sample
```

Replace with:

```python
from .attitude_widget import AttitudeIndicator
from .log_format import Sample
from .serial_source import SerialReader, list_serial_ports
```

Find:

```python
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
```

Replace with:

```python
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
```

- [ ] **Step 2: Add the serial control bar to `__init__`**

Find:

```python
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.addWidget(tabs, stretch=3)
        content_layout.addWidget(side_panel, stretch=1)
        self.setCentralWidget(content)

        self._skipped_count = 0
        self._logging_started = False
        self.statusBar().showMessage("Not connected")
```

Replace with:

```python
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.addWidget(tabs, stretch=3)
        content_layout.addWidget(side_panel, stretch=1)

        self._skipped_count = 0
        self._logging_started = False
        self._serial_reader = None
        self.serial_controls = self._build_serial_controls()

        central = QWidget()
        outer_layout = QVBoxLayout(central)
        outer_layout.addWidget(self.serial_controls)
        outer_layout.addWidget(content)
        self.setCentralWidget(central)

        self.statusBar().showMessage("Not connected")
```

- [ ] **Step 3: Add the serial control methods**

Add these methods to the `MainWindow` class (after `on_skipped_line`):

```python
    def _build_serial_controls(self) -> QWidget:
        box = QGroupBox("Live Serial")
        self.port_combo = QComboBox()
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["9600", "19200", "38400", "57600", "115200", "230400"])
        self.baud_combo.setCurrentText("115200")
        self.refresh_button = QPushButton("Refresh Ports")
        self.connect_button = QPushButton("Connect")
        self.refresh_button.clicked.connect(self.refresh_ports)
        self.connect_button.clicked.connect(self.toggle_serial_connection)

        layout = QHBoxLayout(box)
        layout.addWidget(QLabel("Port:"))
        layout.addWidget(self.port_combo)
        layout.addWidget(QLabel("Baud:"))
        layout.addWidget(self.baud_combo)
        layout.addWidget(self.refresh_button)
        layout.addWidget(self.connect_button)

        self.refresh_ports()
        return box

    def refresh_ports(self) -> None:
        self.port_combo.clear()
        self.port_combo.addItems(list_serial_ports())

    def toggle_serial_connection(self) -> None:
        if self._serial_reader is not None:
            self.disconnect_serial()
        else:
            self.connect_serial()

    def connect_serial(self) -> None:
        port = self.port_combo.currentText()
        if not port:
            self.statusBar().showMessage("No serial port selected")
            return
        baud = int(self.baud_combo.currentText())
        self._logging_started = False
        self._skipped_count = 0
        self._serial_reader = SerialReader(port, baud)
        self._serial_reader.sample_received.connect(self.on_sample)
        self._serial_reader.boot_line.connect(self.on_boot_line)
        self._serial_reader.skipped_line.connect(self.on_skipped_line)
        self._serial_reader.error.connect(self.on_serial_error)
        self._serial_reader.start()
        self.connect_button.setText("Disconnect")
        self.statusBar().showMessage("Waiting for system check...")

    def disconnect_serial(self) -> None:
        if self._serial_reader is not None:
            self._serial_reader.stop()
            self._serial_reader = None
        self.connect_button.setText("Connect")
        self.statusBar().showMessage("Not connected")

    def on_serial_error(self, message: str) -> None:
        self.statusBar().showMessage(f"Serial error: {message}")
        self.disconnect_serial()
```

- [ ] **Step 4: Manually verify**

Run: `python -m arduino_viz.main`
Expected: a "Live Serial" bar appears above the plots with Port/Baud dropdowns and Connect button.
- Click "Refresh Ports" — your board's COM port should appear (if plugged in).
- Select it and click "Connect" — status bar should show boot lines (e.g. "BMP280 Online") as they arrive, then switch to "Logging — N skipped lines" once real data starts, and plots/attitude/readout should update live.
- Click "Disconnect" (button now reads "Disconnect") — status bar returns to "Not connected".
- If no board is available, select an invalid/nonexistent port and click Connect — status bar should show a serial error message and the button should reset to "Connect".

- [ ] **Step 5: Commit**

```bash
git add arduino_viz/main_window.py
git commit -m "feat: wire live serial controls into main window"
```

---

### Task 8: File playback wiring

**Files:**
- Modify: `arduino_viz/main_window.py`

**Interfaces:**
- Consumes: `load_log_file`, `LogFileFormatError`, `LogPlayer` from `arduino_viz.file_source`; `MainWindow.serial_controls`, `disconnect_serial` from Task 7.
- Produces: `MainWindow.mode_combo`, `source_stack`, `file_controls`; methods `open_log_file()`, `toggle_playback()`, `stop_file_playback()`, `_on_speed_changed(text)`, `_on_scrub(index)`, `_on_playback_sample(index, sample)`, `_on_playback_finished()`, `_on_mode_changed(index)`.

- [ ] **Step 1: Add imports**

Find:

```python
from .log_format import Sample
from .serial_source import SerialReader, list_serial_ports
```

Replace with:

```python
from .file_source import LogFileFormatError, LogPlayer, load_log_file
from .log_format import Sample
from .serial_source import SerialReader, list_serial_ports
```

Find:

```python
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
```

Replace with:

```python
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
```

- [ ] **Step 2: Replace the top bar with a mode-switching stack**

Find:

```python
        self._skipped_count = 0
        self._logging_started = False
        self._serial_reader = None
        self.serial_controls = self._build_serial_controls()

        central = QWidget()
        outer_layout = QVBoxLayout(central)
        outer_layout.addWidget(self.serial_controls)
        outer_layout.addWidget(content)
        self.setCentralWidget(central)

        self.statusBar().showMessage("Not connected")
```

Replace with:

```python
        self._skipped_count = 0
        self._logging_started = False
        self._serial_reader = None
        self._log_player = None
        self.serial_controls = self._build_serial_controls()
        self.file_controls = self._build_file_controls()

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Live Serial", "Load File"])
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self.source_stack = QStackedWidget()
        self.source_stack.addWidget(self.serial_controls)
        self.source_stack.addWidget(self.file_controls)

        top_bar = QWidget()
        top_layout = QHBoxLayout(top_bar)
        top_layout.addWidget(QLabel("Source:"))
        top_layout.addWidget(self.mode_combo)
        top_layout.addWidget(self.source_stack, stretch=1)

        central = QWidget()
        outer_layout = QVBoxLayout(central)
        outer_layout.addWidget(top_bar)
        outer_layout.addWidget(content)
        self.setCentralWidget(central)

        self.statusBar().showMessage("Not connected")
```

- [ ] **Step 3: Add the file control methods**

Add these methods to the `MainWindow` class (after `on_serial_error`):

```python
    def _build_file_controls(self) -> QWidget:
        box = QGroupBox("Load File")
        self.open_file_button = QPushButton("Open File...")
        self.play_button = QPushButton("Play")
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.5x", "1x", "2x", "4x", "10x"])
        self.speed_combo.setCurrentText("1x")
        self.scrub_slider = QSlider(Qt.Horizontal)
        self.scrub_slider.setEnabled(False)

        self.open_file_button.clicked.connect(self.open_log_file)
        self.play_button.clicked.connect(self.toggle_playback)
        self.speed_combo.currentTextChanged.connect(self._on_speed_changed)
        self.scrub_slider.sliderMoved.connect(self._on_scrub)

        layout = QHBoxLayout(box)
        layout.addWidget(self.open_file_button)
        layout.addWidget(self.play_button)
        layout.addWidget(QLabel("Speed:"))
        layout.addWidget(self.speed_combo)
        layout.addWidget(self.scrub_slider, stretch=1)

        return box

    def _on_mode_changed(self, index: int) -> None:
        self.source_stack.setCurrentIndex(index)
        if index == 0:
            self.stop_file_playback()
        else:
            self.disconnect_serial()

    def open_log_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Log File", "", "Log files (*.txt *.log *.csv);;All files (*)"
        )
        if not path:
            return
        try:
            samples = load_log_file(path)
        except LogFileFormatError as exc:
            QMessageBox.critical(self, "Invalid log file", str(exc))
            return

        self.stop_file_playback()
        self._logging_started = False
        self._skipped_count = 0
        self.scrub_slider.setEnabled(True)
        self.scrub_slider.setRange(0, len(samples) - 1)
        self.scrub_slider.setValue(0)

        self._log_player = LogPlayer(samples)
        self._log_player.sample_ready.connect(self._on_playback_sample)
        self._log_player.finished.connect(self._on_playback_finished)
        self._on_speed_changed(self.speed_combo.currentText())
        self.play_button.setText("Play")
        self.statusBar().showMessage(f"Loaded {len(samples)} samples from {path}")

    def toggle_playback(self) -> None:
        if self._log_player is None:
            return
        if self.play_button.text() == "Play":
            self._log_player.play()
            self.play_button.setText("Pause")
        else:
            self._log_player.pause()
            self.play_button.setText("Play")

    def stop_file_playback(self) -> None:
        if self._log_player is not None:
            self._log_player.pause()
        if hasattr(self, "play_button"):
            self.play_button.setText("Play")

    def _on_speed_changed(self, text: str) -> None:
        if self._log_player is not None:
            self._log_player.set_speed(float(text.rstrip("x")))

    def _on_scrub(self, index: int) -> None:
        if self._log_player is not None:
            self._log_player.seek(index)

    def _on_playback_sample(self, index: int, sample) -> None:
        self.on_sample(sample)
        self.scrub_slider.blockSignals(True)
        self.scrub_slider.setValue(index)
        self.scrub_slider.blockSignals(False)

    def _on_playback_finished(self) -> None:
        self.play_button.setText("Play")
        self.statusBar().showMessage("Playback finished")
```

- [ ] **Step 4: Manually verify**

Run: `python -m arduino_viz.main`
Expected: a "Source:" dropdown now sits above the controls, switching between "Live Serial" and "Load File" bars.
- Switch to "Load File", click "Open File...", pick any log file matching the pipe format (Task 9 will provide a ready-made one) — status bar shows "Loaded N samples from ...".
- Click "Play" — plots/attitude/readout update over time at recorded pace, scrub slider advances, button reads "Pause".
- Click "Pause" — playback stops advancing.
- Change the speed dropdown while playing — playback visibly speeds up/slows down.
- Drag the scrub slider — `seek()` repositions playback (verify by resuming Play after a manual scrub).
- Let it run to the end — status bar shows "Playback finished".
- Switch back to "Live Serial" — file playback stops automatically (per `_on_mode_changed`).

- [ ] **Step 5: Commit**

```bash
git add arduino_viz/main_window.py
git commit -m "feat: wire file playback controls and source-mode switch"
```

---

### Task 9: Sample data & end-to-end manual verification

**Files:**
- Create: `scripts/generate_sample_log.py`
- Create: `sample_data/sample_log.txt` (generated by the script)

**Interfaces:**
- Consumes: the full app (Tasks 1–8).
- Produces: a reproducible sample log file for exercising the file-playback path without needing the board attached.

- [ ] **Step 1: Implement `scripts/generate_sample_log.py`**

```python
"""Generate a synthetic sample log file for manual testing of file playback."""
import math
import os

BOOT_LINES = [
    "Initializing Pins",
    "Initializing BMP",
    "BMP ID was: 0x58",
    "Launch pressure: 1015.42",
    "Initializing MPU1",
    ">*****..........>..........These are the Active offsets: ",
    "1064.00000,    -1229.00000,    4674.00000,    90.00000,    -71.00000,    25.00000",
    "",
    "Initializing MPU2",
    ">*****..........>..........These are the Active offsets: ",
    "",
    "-3434.00000,    -2011.00000,    4028.00000,    344.00000,    55.00000,    -13.00000",
    "",
    "Chip ID: 0x58",
    "BMP280 Online",
    "MPU1 Online",
    "MPU2 Online",
    "System check complete. Logging started.",
]

HEADER = "  TIME  | TEMP |  ALT | BARO | PITCH | ROLL  |  ACCX  |  ACCY  |  ACCZ  |  GYRX  |  GYRY  |  GYRZ"


def generate_data_lines(count: int = 200, step_ms: int = 32) -> list[str]:
    lines = []
    time_ms = 2
    for i in range(count):
        pitch = 0.02 * math.sin(i / 15)
        roll = 0.03 * math.cos(i / 12)
        accx = 0.01 * math.sin(i / 8)
        accy = 0.02 * math.cos(i / 8)
        accz = 0.9996 + 0.001 * math.sin(i / 30)
        gyrx = 0.05 * math.sin(i / 5)
        gyry = 0.02 * math.cos(i / 6)
        gyrz = -0.09 + 0.01 * math.sin(i / 4)
        temp = 80 + (i // 20)
        line = (
            f"{time_ms:06d} | {temp:04d} | 0000 | 1015 | "
            f"{pitch:.3f} | {roll:.3f} | {accx:.4f} | {accy:.4f} | {accz:.4f} | "
            f"{gyrx:.4f} | {gyry:.4f} | {gyrz:.4f}"
        )
        lines.append(line)
        time_ms += step_ms
    return lines


def main() -> None:
    os.makedirs("sample_data", exist_ok=True)
    lines = BOOT_LINES + [HEADER] + generate_data_lines()
    with open("sample_data/sample_log.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote sample_data/sample_log.txt with {len(lines)} lines")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Generate the sample file**

Run: `python scripts/generate_sample_log.py`
Expected: prints `Wrote sample_data/sample_log.txt with 219 lines`, and the file exists.

- [ ] **Step 3: End-to-end manual verification**

Run: `python -m arduino_viz.main`
- Switch to "Load File", click "Open File...", select `sample_data/sample_log.txt`.
- Status bar shows "Loaded 200 samples from ...".
- Click "Play" — all three plot tabs should show smooth scrolling sine-like curves, the attitude indicator should gently rock, and the numeric readout should update continuously. Total playback should take roughly `200 * 32ms` ≈ 6.4 seconds at 1x speed.
- Try 4x and 0.5x speed while playing to confirm the pace visibly changes.
- Let it finish and confirm "Playback finished" appears.
- If the board is available, repeat Task 7's live-serial manual check now as a final full-system sanity pass.

- [ ] **Step 4: Commit**

```bash
git add scripts/generate_sample_log.py sample_data/sample_log.txt
git commit -m "test: add synthetic sample log and complete manual e2e verification"
```
