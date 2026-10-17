# Postflight Vis — Events, Airspeed/Yaw/G-load, Attitude Detail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resync the `arduino_viz` postflight visualizer with the current `.ino` log format, add a flight-event pipeline (5 one-shot indicator boxes + a launch-conditions overlay on the plots), true per-axis g-load, and richer attitude-indicator detail (yaw, pitch ladder, compass ring, numeric overlay).

**Architecture:** One small `.ino` addition (log 3 more raw-g columns that are already computed) plus a straight-line update through the existing pipeline: `log_format.py` (parser) → `file_source.py` / `serial_source.py` (both data sources) → new `event_panel.py` widget + extended `attitude_widget.py` → `main_window.py` (wiring). No new dependencies.

**Tech Stack:** PySide6, pyqtgraph, pyserial, pytest (all already in `requirements.txt`); Arduino/C++ for the `.ino`.

**Spec:** `docs/superpowers/specs/2026-09-01-postflight-vis-events-and-dials-design.md`

## Global Constraints

- No new dependencies — everything is built from PySide6/pyqtgraph/pyserial already in `requirements.txt`, or the standard library.
- `Sample` field names are locked by the spec's schema table: `temp_f`, `alt_ft` (renamed from `temp_c`/`alt_m`), plus new `yaw`, `gx_raw`, `gy_raw`, `gz_raw`, `airspeed_fps`. `accx/accy/accz` keep their existing meaning (unit-vector direction, NOT g-force).
- Event names are matched by prefix (`name.startswith(key)`), never exact equality — `"CHUTE DEPLOY (inferred)"` must match the `"CHUTE DEPLOY"` box.
- Ordering guarantee the pipeline code relies on: an `>>> EVENT: ...` line always precedes its matching-timestep data line, both live and in a replayed file. `LogPlayer` must fire due events before emitting the sample at/after their timestep, not after.
- No automated tests for Qt widgets (`AttitudeIndicator`, `EventPanel`, `MainWindow`) — matches this project's existing convention (only the pure-logic `log_format.py`/`file_source.py` have pytest coverage). Widget tasks are verified manually with a runnable snippet instead.
- Event boxes are one-shot latches for the session/file — no un-latching on scrub-back, no replaying skipped events on seek.
- Only launch conditions (liftoff time + altitude) are overlaid on the plots — not all 5 events; the event panel covers the other four.

---

### Task 1: `.ino` — log raw g-load columns

**Files:**
- Modify: `D:\Conor Rowland Game Dev Work\Programming work\Hephaestus Flight Computer\src\Hephaestus_V1\Hephaestus_V1.ino:231-236,401,420,448-461`

**Interfaces:**
- Produces: the live/logged data line now has 17 pipe-delimited fields in this exact order: `TIME | TEMP | ALT | BARO | PITCH | ROLL | YAW | ACCX | ACCY | ACCZ | GX | GY | GZ | GYRX | GYRY | GYRZ | AIRSPD`. `GX/GY/GZ` are `accelRawMapped.x/y/z` (g's, true magnitude) — already computed in `loop()` for the airspeed filter, just newly printed.

- [ ] **Step 1: Widen `formatpacket`'s signature to accept the raw g vector**

In `Hephaestus_V1.ino`, change line 420 from:

```cpp
void formatpacket(int16_t time, float temp, float alt, float baro, Vector3 accel, Vector3 gyro, float airspeed)
```

to:

```cpp
void formatpacket(int16_t time, float temp, float alt, float baro, Vector3 accel, Vector3 gyro, float airspeed, Vector3 gRaw)
```

- [ ] **Step 2: Pass `accelRawMapped` at the call site**

Change line 401 from:

```cpp
  formatpacket(logstep,temp,altitude,P_now,accel,gyro,airspeed);
```

to:

```cpp
  formatpacket(logstep,temp,altitude,P_now,accel,gyro,airspeed,accelRawMapped);
```

- [ ] **Step 3: Print GX/GY/GZ between the ACCEL and GYRO blocks**

In `formatpacket`, insert this new block immediately after the existing `//------------------------------------------- ACCEL X Y Z LOG` block (after the `Serial.print(accel.z , 4); Serial.print(" | ");` lines, currently lines 452-454) and before the `//------------------------------------------- GYRO X Y Z LOG` comment:

```cpp
//------------------------------------------- RAW G LOAD X Y Z LOG -------------------------------------------------
  Serial.print(gRaw.x , 4);
  Serial.print(" | ");
  Serial.print(gRaw.y , 4);
  Serial.print(" | ");
  Serial.print(gRaw.z , 4);
  Serial.print(" | ");
```

- [ ] **Step 4: Update the header line and format-reference comment**

Change line 236 from:

```cpp
  Serial.println("  TIME  | TEMP |  ALT | BARO | PITCH | ROLL  | YAW  |  ACCX  |  ACCY  |  ACCZ  |  GYRX  |  GYRY  |  GYRZ | AIRSPD");
```

to:

```cpp
  Serial.println("  TIME  | TEMP |  ALT | BARO | PITCH | ROLL  | YAW  |  ACCX  |  ACCY  |  ACCZ  |  GX  |  GY  |  GZ  |  GYRX  |  GYRY  |  GYRZ | AIRSPD");
```

And update the comment block at lines 231-235 from:

```cpp
  // Log format (pipe-delimited): TIME(logstep) | TEMP(F) | ALT(ft) | BARO(hPa) |
  // PITCH/ROLL/YAW(deg) | ACCX/Y/Z(g, unit vector, tilt-relative not physical) |
  // GYRX/Y/Z(deg/s) | AIRSPD(ft/s, vertical velocity estimate)
  // Event lines are emitted out-of-band as ">>> EVENT: <name> at t=<logstep>" and
  // do not match this column format -- a parser should special-case the ">>>" prefix.
```

to:

```cpp
  // Log format (pipe-delimited): TIME(logstep) | TEMP(F) | ALT(ft) | BARO(hPa) |
  // PITCH/ROLL/YAW(deg) | ACCX/Y/Z(g, unit vector, tilt-relative not physical) |
  // GX/GY/GZ(g, true magnitude, vertical-axis-remapped raw accel) |
  // GYRX/Y/Z(deg/s) | AIRSPD(ft/s, vertical velocity estimate)
  // Event lines are emitted out-of-band as ">>> EVENT: <name> at t=<logstep>" and
  // do not match this column format -- a parser should special-case the ">>>" prefix.
```

- [ ] **Step 5: Verify manually (no compiler in this environment)**

Re-read the modified file and count the fields in the new header string — must be exactly 17, in the order: `TIME, TEMP, ALT, BARO, PITCH, ROLL, YAW, ACCX, ACCY, ACCZ, GX, GY, GZ, GYRX, GYRY, GYRZ, AIRSPD`. Confirm `formatpacket`'s print calls emit values in that same order (this is what Task 2's parser will assume). Once you next flash the board, confirm the Serial Monitor's actual output matches.

- [ ] **Step 6: Commit (in the Hephaestus Flight Computer repo, not PythonProject)**

```bash
cd "D:\Conor Rowland Game Dev Work\Programming work\Hephaestus Flight Computer"
git add src/Hephaestus_V1/Hephaestus_V1.ino
git commit -m "feat: log raw g-load (GX/GY/GZ) alongside existing telemetry"
```

---

### Task 2: `log_format.py` — resync parser to the 17-field format + event parsing

**Files:**
- Modify: `arduino_viz/log_format.py`
- Test: `tests/test_log_format.py`

**Interfaces:**
- Consumes: nothing (pure parsing module).
- Produces: `Sample` dataclass with fields `time_ms: int, temp_f: float, alt_ft: float, baro_hpa: float, pitch: float, roll: float, yaw: float, accx: float, accy: float, accz: float, gx_raw: float, gy_raw: float, gz_raw: float, gyrx: float, gyry: float, gyrz: float, airspeed_fps: float`. `parse_line(line: str) -> Optional[Sample]`. `parse_event_line(line: str) -> Optional[tuple[str, int]]` returning `(name, time_step)`.

- [ ] **Step 1: Replace `tests/test_log_format.py` with tests for the new schema**

```python
from arduino_viz.log_format import parse_line, parse_event_line, Sample


def test_parses_valid_data_line():
    line = (
        "000002 | 72.5 | 3.2 | 1015.4 | 0.003 | -0.001 | 0.010 | "
        "0.0027 | 0.0263 | 0.9996 | 0.05 | 0.02 | 1.01 | "
        "0.0762 | 0.0152 | -0.0915 | 12.34"
    )
    assert parse_line(line) == Sample(
        time_ms=2, temp_f=72.5, alt_ft=3.2, baro_hpa=1015.4,
        pitch=0.003, roll=-0.001, yaw=0.010,
        accx=0.0027, accy=0.0263, accz=0.9996,
        gx_raw=0.05, gy_raw=0.02, gz_raw=1.01,
        gyrx=0.0762, gyry=0.0152, gyrz=-0.0915,
        airspeed_fps=12.34,
    )


def test_strips_ide_timestamp_prefix():
    line = (
        "20:55:50.470 -> 000002 | 72.5 | 3.2 | 1015.4 | 0.003 | -0.001 | 0.010 | "
        "0.0027 | 0.0263 | 0.9996 | 0.05 | 0.02 | 1.01 | "
        "0.0762 | 0.0152 | -0.0915 | 12.34"
    )
    assert parse_line(line) is not None


def test_negative_values_line():
    line = (
        "000003 | 72.5 | 3.2 | 1015.4 | 0.005 | -0.004 | -0.020 | "
        "0.0008 | 0.0269 | 0.9996 | -0.02 | 0.01 | 0.99 | "
        "-0.0152 | -0.0610 | -0.0457 | -5.5"
    )
    sample = parse_line(line)
    assert sample.roll == -0.004
    assert sample.gyrz == -0.0457
    assert sample.airspeed_fps == -5.5


def test_rejects_column_header_line():
    line = (
        "  TIME  | TEMP |  ALT | BARO | PITCH | ROLL  | YAW  |  ACCX  |  ACCY  "
        "|  ACCZ  |  GX  |  GY  |  GZ  |  GYRX  |  GYRY  |  GYRZ | AIRSPD"
    )
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
    line = (
        "000002 | 72.5 | 3.2 | 1015.4 | 0.003 | -0.001 | 0.010 | "
        "0.0027 | 0.0263 | 0.9996 | 0.05 | 0.02 | 1.01 | "
        "0.0762 | 0.0152 | -0.0915"
    )
    assert parse_line(line) is None


def test_rejects_event_line_as_data():
    assert parse_line(">>> EVENT: LIFTOFF at t=42") is None


def test_parses_simple_event_line():
    assert parse_event_line(">>> EVENT: LIFTOFF at t=42") == ("LIFTOFF", 42)


def test_parses_event_line_with_parenthesized_qualifier():
    assert parse_event_line(">>> EVENT: CHUTE DEPLOY (inferred) at t=890") == (
        "CHUTE DEPLOY (inferred)", 890,
    )


def test_parses_all_five_event_names():
    for name in ("LIFTOFF", "BURNOUT", "APOGEE", "CHUTE DEPLOY (inferred)", "LANDED"):
        line = f">>> EVENT: {name} at t=1"
        assert parse_event_line(line) == (name, 1)


def test_event_line_rejects_non_event_text():
    assert parse_event_line("BMP280 Online") is None
    assert parse_event_line("000002 | 72.5 | 3.2") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_log_format.py -v`
Expected: FAIL — `Sample.__init__()` rejects `temp_f`/`yaw`/etc. (unexpected keyword arguments), and `parse_event_line` doesn't exist (`ImportError`).

- [ ] **Step 3: Rewrite `arduino_viz/log_format.py`**

```python
import re
from dataclasses import dataclass
from typing import Optional

_TIMESTAMP_PREFIX = re.compile(r"^\d{2}:\d{2}:\d{2}\.\d{3}\s*->\s*")
_EVENT_LINE = re.compile(r"^>>> EVENT: (.+?) at t=(\d+)\s*$")
_FIELD_COUNT = 17


@dataclass
class Sample:
    time_ms: int
    temp_f: float
    alt_ft: float
    baro_hpa: float
    pitch: float
    roll: float
    yaw: float
    accx: float
    accy: float
    accz: float
    gx_raw: float
    gy_raw: float
    gz_raw: float
    gyrx: float
    gyry: float
    gyrz: float
    airspeed_fps: float


def parse_line(line: str) -> Optional[Sample]:
    """Parse one line of the board's log format into a Sample.

    Returns None for anything that isn't a full 17-field numeric data
    line (header line, blank line, boot/calibration text, event line)
    rather than raising, since the boot sequence is arbitrary free text
    with no fixed set of messages to match against.
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

    (time_raw, temp_f, alt_ft, baro_hpa, pitch, roll, yaw,
     accx, accy, accz, gx_raw, gy_raw, gz_raw,
     gyrx, gyry, gyrz, airspeed_fps) = values

    return Sample(
        time_ms=int(time_raw),
        temp_f=temp_f,
        alt_ft=alt_ft,
        baro_hpa=baro_hpa,
        pitch=pitch,
        roll=roll,
        yaw=yaw,
        accx=accx,
        accy=accy,
        accz=accz,
        gx_raw=gx_raw,
        gy_raw=gy_raw,
        gz_raw=gz_raw,
        gyrx=gyrx,
        gyry=gyry,
        gyrz=gyrz,
        airspeed_fps=airspeed_fps,
    )


def parse_event_line(line: str) -> Optional[tuple[str, int]]:
    """Parse a '>>> EVENT: <name> at t=<step>' line into (name, time_step).

    Returns None for anything else. Callers should match `name` loosely
    (e.g. str.startswith) since it can carry a qualifier such as
    "CHUTE DEPLOY (inferred)".
    """
    match = _EVENT_LINE.match(line.strip())
    if match is None:
        return None
    name, time_step = match.groups()
    return name, int(time_step)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_log_format.py -v`
Expected: PASS (all tests green).

- [ ] **Step 5: Commit**

```bash
git add arduino_viz/log_format.py tests/test_log_format.py
git commit -m "feat: resync log parser to 17-field format, add event-line parsing"
```

---

### Task 3: `file_source.py` — carry events through file replay

**Files:**
- Modify: `arduino_viz/file_source.py`
- Test: `tests/test_file_source.py`

**Interfaces:**
- Consumes: `Sample`, `parse_line`, `parse_event_line` from Task 2 (`arduino_viz.log_format`).
- Produces: `load_log_file(path: str) -> tuple[list[Sample], list[tuple[int, str]]]` (samples, events-sorted-by-time_step). `LogPlayer(samples, events=None, parent=None)` gains signal `event_ready = Signal(str)`, emitted for every due event immediately before the `sample_ready` of the first sample at/after that event's time_step (never after).

- [ ] **Step 1: Replace `tests/test_file_source.py` with tests for the new return shape and event ordering**

```python
from PySide6.QtCore import QCoreApplication
import pytest

from arduino_viz.file_source import LogFileFormatError, LogPlayer, load_log_file, _delay_ms
from arduino_viz.log_format import Sample

# LogPlayer is a QObject/QTimer; PySide6 wants a QCoreApplication to exist
# before constructing one, even though this test never runs an event loop.
_app = QCoreApplication.instance() or QCoreApplication([])


def _sample(time_ms):
    return Sample(
        time_ms=time_ms, temp_f=0, alt_ft=0, baro_hpa=0, pitch=0, roll=0, yaw=0,
        accx=0, accy=0, accz=0, gx_raw=0, gy_raw=0, gz_raw=0,
        gyrx=0, gyry=0, gyrz=0, airspeed_fps=0,
    )


_DATA_LINE = (
    "{time} | 72.5 | 3.2 | 1015.4 | 0.003 | -0.000 | 0.010 | "
    "0.0027 | 0.0263 | 0.9996 | 0.05 | 0.02 | 1.01 | "
    "0.0762 | 0.0152 | -0.0915 | 12.34"
)


def test_load_log_file_returns_samples_and_events(tmp_path):
    content = (
        "Initializing Pins\n"
        "BMP280 Online\n"
        "System check complete. Logging started.\n"
        "  TIME  | TEMP |  ALT | BARO | PITCH | ROLL  | YAW  |  ACCX  |  ACCY  "
        "|  ACCZ  |  GX  |  GY  |  GZ  |  GYRX  |  GYRY  |  GYRZ | AIRSPD\n"
        + _DATA_LINE.format(time="000001") + "\n"
        ">>> EVENT: LIFTOFF at t=2\n"
        + _DATA_LINE.format(time="000002") + "\n"
    )
    log_file = tmp_path / "sample.txt"
    log_file.write_text(content, encoding="utf-8")

    samples, events = load_log_file(str(log_file))

    assert len(samples) == 2
    assert samples[0].time_ms == 1
    assert samples[1].time_ms == 2
    assert events == [(2, "LIFTOFF")]


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


def test_log_player_fires_event_before_matching_sample():
    samples = [_sample(1), _sample(2), _sample(3)]
    events = [(2, "LIFTOFF")]
    player = LogPlayer(samples, events)

    received = []
    player.event_ready.connect(lambda name: received.append(("event", name)))
    player.sample_ready.connect(lambda i, s: received.append(("sample", s.time_ms)))

    player._emit_next()  # time_ms=1, no event due yet
    player._emit_next()  # time_ms=2, LIFTOFF is due first
    assert received == [
        ("sample", 1),
        ("event", "LIFTOFF"),
        ("sample", 2),
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_file_source.py -v`
Expected: FAIL — `load_log_file` still returns a bare list (unpacking into `samples, events` raises), and `LogPlayer` has no `event_ready` signal.

- [ ] **Step 3: Rewrite `arduino_viz/file_source.py`**

```python
from PySide6.QtCore import QObject, QTimer, Signal

from .log_format import Sample, parse_event_line, parse_line


class LogFileFormatError(Exception):
    pass


def load_log_file(path: str) -> tuple[list[Sample], list[tuple[int, str]]]:
    samples: list[Sample] = []
    events: list[tuple[int, str]] = []
    first_line = None
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for raw_line in f:
            stripped = raw_line.strip()
            if first_line is None and stripped:
                first_line = stripped

            sample = parse_line(raw_line)
            if sample is not None:
                samples.append(sample)
                continue

            event = parse_event_line(raw_line)
            if event is not None:
                events.append(event)

    if not samples:
        raise LogFileFormatError(
            f"No valid data lines found in file. First line: {first_line!r}"
        )
    events.sort(key=lambda e: e[0])
    return samples, events


def _delay_ms(prev: Sample, next_: Sample, speed: float) -> int:
    delta = next_.time_ms - prev.time_ms
    return max(0, int(delta / speed))


class LogPlayer(QObject):
    sample_ready = Signal(int, object)  # index, Sample
    event_ready = Signal(str)  # event name
    finished = Signal()

    def __init__(self, samples: list[Sample], events: list[tuple[int, str]] = None, parent=None):
        super().__init__(parent)
        self._samples = samples
        self._events = events or []
        self._event_cursor = 0
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

        while (
            self._event_cursor < len(self._events)
            and self._events[self._event_cursor][0] <= sample.time_ms
        ):
            _, name = self._events[self._event_cursor]
            self.event_ready.emit(name)
            self._event_cursor += 1

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
Expected: PASS (all tests green).

- [ ] **Step 5: Commit**

```bash
git add arduino_viz/file_source.py tests/test_file_source.py
git commit -m "feat: carry flight events through file replay, ordered before their sample"
```

---

### Task 4: `serial_source.py` — emit events from the live stream

**Files:**
- Modify: `arduino_viz/serial_source.py`

**Interfaces:**
- Consumes: `parse_event_line` from Task 2.
- Produces: `SerialReader` gains signal `event_received = Signal(str)`, emitted for any line matching `parse_event_line` (instead of being counted via `skipped_line`).

- [ ] **Step 1: Rewrite `arduino_viz/serial_source.py`**

```python
import serial
from PySide6.QtCore import QThread, Signal
from serial.tools import list_ports

from .log_format import parse_event_line, parse_line


def list_serial_ports() -> list[str]:
    return [p.device for p in list_ports.comports()]


class SerialReader(QThread):
    sample_received = Signal(object)  # Sample
    event_received = Signal(str)  # event name
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
                        continue

                    event = parse_event_line(line)
                    if event is not None:
                        name, _time_step = event
                        self.event_received.emit(name)
                    elif not seen_first_sample:
                        stripped = line.strip()
                        if stripped:
                            self.boot_line.emit(stripped)
                    else:
                        self.skipped_line.emit()
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self._running = False

    def stop(self) -> None:
        self._running = False
        self.wait(2000)
```

- [ ] **Step 2: Verify manually**

`serial_source.py` has no automated tests in this project (it does real serial I/O) — same as before this change. Confirm by inspection that the new `event` branch sits before the `boot_line`/`skipped_line` fallback, so an event line is never miscounted as skipped. Full behavioral confirmation happens in Task 7's manual pass, once `MainWindow` is wired to `event_received`.

- [ ] **Step 3: Commit**

```bash
git add arduino_viz/serial_source.py
git commit -m "feat: emit flight events from the live serial stream"
```

---

### Task 5: `event_panel.py` — new event indicator widget

**Files:**
- Create: `arduino_viz/event_panel.py`

**Interfaces:**
- Produces: `EventPanel(QWidget)` with `light(name: str) -> None` (lights the box whose key `name` starts with; idempotent) and `reset() -> None` (all boxes back to unlit).

- [ ] **Step 1: Create `arduino_viz/event_panel.py`**

```python
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

_BOX_KEYS = ["LIFTOFF", "BURNOUT", "APOGEE", "CHUTE DEPLOY", "LANDED"]
_UNLIT_STYLE = "background-color: #444; color: white; padding: 4px; border-radius: 3px;"
_LIT_STYLE = "background-color: #2ecc71; color: black; padding: 4px; border-radius: 3px;"


class EventPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._boxes: dict[str, QLabel] = {}
        layout = QHBoxLayout(self)
        for key in _BOX_KEYS:
            label = QLabel(key)
            label.setStyleSheet(_UNLIT_STYLE)
            self._boxes[key] = label
            layout.addWidget(label)

    def light(self, name: str) -> None:
        for key, label in self._boxes.items():
            if name.startswith(key):
                label.setStyleSheet(_LIT_STYLE)
                return

    def reset(self) -> None:
        for label in self._boxes.values():
            label.setStyleSheet(_UNLIT_STYLE)
```

- [ ] **Step 2: Verify manually**

Run:

```bash
python -c "from PySide6.QtWidgets import QApplication; from arduino_viz.event_panel import EventPanel; app = QApplication([]); p = EventPanel(); p.light('CHUTE DEPLOY (inferred)'); print('CHUTE lit:', 'lit' if '2ecc71' in p._boxes['CHUTE DEPLOY'].styleSheet() else 'unlit'); print('LIFTOFF lit:', 'lit' if '2ecc71' in p._boxes['LIFTOFF'].styleSheet() else 'unlit'); p.reset(); print('CHUTE after reset:', 'lit' if '2ecc71' in p._boxes['CHUTE DEPLOY'].styleSheet() else 'unlit')"
```

Expected output:
```
CHUTE lit: lit
LIFTOFF lit: unlit
CHUTE after reset: unlit
```

- [ ] **Step 3: Commit**

```bash
git add arduino_viz/event_panel.py
git commit -m "feat: add EventPanel widget for flight-event indicator boxes"
```

---

### Task 6: `attitude_widget.py` — yaw, pitch ladder, compass ring, numeric overlay

**Files:**
- Modify: `arduino_viz/attitude_widget.py`

**Interfaces:**
- Produces: `AttitudeIndicator.set_orientation(pitch: float, roll: float, yaw: float) -> None` — note the signature now requires `yaw`; `main_window.py`'s existing 2-arg call becomes invalid until Task 7 updates it (expected — verify this task standalone, not through the full app).

- [ ] **Step 1: Rewrite `arduino_viz/attitude_widget.py`**

```python
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


class AttitudeIndicator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pitch = 0.0  # degrees
        self._roll = 0.0  # degrees
        self._yaw = 0.0  # degrees
        self.setMinimumSize(150, 150)

    def set_orientation(self, pitch: float, roll: float, yaw: float) -> None:
        self._pitch = pitch
        self._roll = roll
        self._yaw = yaw
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height())
        painter.translate(self.width() / 2, self.height() / 2)

        pitch_deg = self._pitch
        roll_deg = self._roll
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

        self._draw_pitch_ladder(painter, side, pixels_per_degree)
        painter.restore()

        self._draw_yaw_ring(painter, side)

        painter.setPen(QPen(Qt.yellow, 3))
        painter.drawLine(QPointF(-side * 0.25, 0), QPointF(-side * 0.08, 0))
        painter.drawLine(QPointF(side * 0.08, 0), QPointF(side * 0.25, 0))
        painter.drawEllipse(QPointF(0, 0), 3, 3)

        self._draw_numeric_overlay(painter, side)

    def _draw_pitch_ladder(self, painter: QPainter, side: float, pixels_per_degree: float) -> None:
        painter.setPen(QPen(Qt.white, 1))
        font = QFont()
        font.setPointSize(max(6, int(side * 0.05)))
        painter.setFont(font)
        for deg in range(-80, 81, 10):
            if deg == 0:
                continue
            y = -deg * pixels_per_degree
            half_width = side * (0.12 if deg % 30 == 0 else 0.06)
            painter.drawLine(QPointF(-half_width, y), QPointF(half_width, y))
            if deg % 30 == 0:
                painter.drawText(QPointF(half_width + 4, y + 4), str(deg))

    def _draw_yaw_ring(self, painter: QPainter, side: float) -> None:
        radius = side * 0.42
        painter.save()
        painter.rotate(-self._yaw)
        painter.setPen(QPen(Qt.white, 1))
        font = QFont()
        font.setPointSize(max(6, int(side * 0.045)))
        painter.setFont(font)
        for heading in range(0, 360, 30):
            painter.save()
            painter.rotate(heading)
            painter.drawLine(QPointF(0, -radius), QPointF(0, -radius + side * 0.05))
            painter.drawText(QPointF(-8, -radius + side * 0.09 + 8), str(heading))
            painter.restore()
        painter.restore()

        painter.setPen(QPen(Qt.red, 2))
        painter.drawLine(QPointF(0, -radius - 4), QPointF(0, -radius + 6))

    def _draw_numeric_overlay(self, painter: QPainter, side: float) -> None:
        painter.setPen(QPen(Qt.white, 1))
        font = QFont()
        font.setPointSize(max(7, int(side * 0.06)))
        painter.setFont(font)
        text = f"P:{self._pitch:.0f} R:{self._roll:.0f} Y:{self._yaw:.0f}"
        painter.drawText(QRectF(-side / 2 + 4, -side / 2 + 4, side - 8, 20), Qt.AlignLeft, text)
```

- [ ] **Step 2: Verify manually**

Run:

```bash
python -c "from PySide6.QtWidgets import QApplication; from arduino_viz.attitude_widget import AttitudeIndicator; app = QApplication([]); w = AttitudeIndicator(); w.resize(300, 300); w.set_orientation(pitch=15, roll=-20, yaw=45); w.show(); app.exec()"
```

Expected: a window showing the horizon tilted/rotated per pitch/roll, degree-marked pitch ladder lines above/below the horizon, a yaw compass ring around the perimeter rotated with a red heading pointer at top, and small text in the top-left reading `P:15 R:-20 Y:45`. Close the window to end the process.

- [ ] **Step 3: Commit**

```bash
git add arduino_viz/attitude_widget.py
git commit -m "feat: add yaw, pitch ladder, compass ring, numeric overlay to attitude indicator"
```

---

### Task 7: `main_window.py` — wire everything together

**Files:**
- Modify: `arduino_viz/main_window.py`
- Create: `sample_data/sample_log_v2.txt` (new-format fixture with a full event sequence, for manual verification)

**Interfaces:**
- Consumes: `Sample` (17 fields, Task 2), `load_log_file` returning `(samples, events)` and `LogPlayer(samples, events)` with `event_ready` (Task 3), `SerialReader.event_received` (Task 4), `EventPanel.light`/`reset` (Task 5), `AttitudeIndicator.set_orientation(pitch, roll, yaw)` (Task 6).
- Produces: fully wired `MainWindow` — no further consumers in this plan.

- [ ] **Step 1: Rewrite `arduino_viz/main_window.py`**

```python
from collections import deque

import pyqtgraph as pg
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

from .attitude_widget import AttitudeIndicator
from .event_panel import EventPanel
from .file_source import LogFileFormatError, LogPlayer, load_log_file
from .log_format import Sample
from .serial_source import SerialReader, list_serial_ports

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
        self._markers = []

    def append(self, time_ms: int, values: dict) -> None:
        self._time.append(time_ms)
        for name, curve in self._curves.items():
            self._channels[name].append(values[name])
            curve.setData(list(self._time), list(self._channels[name]))

    def clear_data(self) -> None:
        # Named clear_data, not clear: pg.PlotWidget.__init__ sets self.clear
        # as an instance attribute (bound to the internal PlotItem.clear),
        # which would silently shadow a same-named method on this subclass.
        self._time.clear()
        for name, curve in self._curves.items():
            self._channels[name].clear()
            curve.setData([], [])
        for marker in self._markers:
            self.removeItem(marker)
        self._markers.clear()

    def add_liftoff_markers(self, time_ms: int, alt_ft: float = None) -> None:
        v_line = pg.InfiniteLine(pos=time_ms, angle=90, pen=pg.mkPen("y", style=Qt.DashLine))
        self.addItem(v_line)
        self._markers.append(v_line)
        if alt_ft is not None:
            h_line = pg.InfiniteLine(pos=alt_ft, angle=0, pen=pg.mkPen("y", style=Qt.DashLine))
            self.addItem(h_line)
            self._markers.append(h_line)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Arduino Telemetry Visualizer")

        self.temp_plot = ChannelGroupPlot(["temp_f"], ["r"], "Temperature (degF)")
        self.alt_plot = ChannelGroupPlot(["alt_ft"], ["g"], "Altitude (ft)")
        self.baro_plot = ChannelGroupPlot(["baro_hpa"], ["b"], "Barometric Pressure (hPa)")

        env_container = QWidget()
        env_layout = QVBoxLayout(env_container)
        env_layout.addWidget(self.temp_plot)
        env_layout.addWidget(self.alt_plot)
        env_layout.addWidget(self.baro_plot)

        self.accel_plot = ChannelGroupPlot(
            ["accx", "accy", "accz"], ["r", "g", "b"], "Accelerometer (direction, unit vector)",
        )
        self.gyro_plot = ChannelGroupPlot(
            ["gyrx", "gyry", "gyrz"], ["r", "g", "b"], "Gyroscope (deg/s)",
        )

        tabs = QTabWidget()
        tabs.addTab(env_container, "Environment")
        tabs.addTab(self.accel_plot, "Accelerometer")
        tabs.addTab(self.gyro_plot, "Gyroscope")

        self.attitude = AttitudeIndicator()
        self.event_panel = EventPanel()
        self.mach_label = QLabel("--")
        self.readout_labels: dict[str, QLabel] = {}
        readout_form = QFormLayout()
        for field in Sample.__dataclass_fields__:
            label = QLabel("--")
            self.readout_labels[field] = label
            readout_form.addRow(field, label)
        readout_form.addRow("mach", self.mach_label)

        side_panel = QWidget()
        side_layout = QVBoxLayout(side_panel)
        side_layout.addWidget(self.attitude)
        side_layout.addWidget(self.event_panel)
        side_layout.addLayout(readout_form)

        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.addWidget(tabs, stretch=3)
        content_layout.addWidget(side_panel, stretch=1)

        self._skipped_count = 0
        self._logging_started = False
        self._serial_reader = None
        self._log_player = None
        self._pending_liftoff = False
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

    def on_sample(self, sample: Sample) -> None:
        self._logging_started = True
        self.temp_plot.append(sample.time_ms, {"temp_f": sample.temp_f})
        self.alt_plot.append(sample.time_ms, {"alt_ft": sample.alt_ft})
        self.baro_plot.append(sample.time_ms, {"baro_hpa": sample.baro_hpa})
        self.accel_plot.append(sample.time_ms, {
            "accx": sample.accx, "accy": sample.accy, "accz": sample.accz,
        })
        self.gyro_plot.append(sample.time_ms, {
            "gyrx": sample.gyrx, "gyry": sample.gyry, "gyrz": sample.gyrz,
        })
        self.attitude.set_orientation(sample.pitch, sample.roll, sample.yaw)

        temp_c = (sample.temp_f - 32) * 5 / 9
        speed_of_sound_mps = 331.3 + 0.6 * temp_c
        airspeed_mps = sample.airspeed_fps / 3.28084
        mach = airspeed_mps / speed_of_sound_mps if speed_of_sound_mps else 0.0
        self.mach_label.setText(f"{mach:.4f}")

        if self._pending_liftoff:
            self.temp_plot.add_liftoff_markers(sample.time_ms)
            self.baro_plot.add_liftoff_markers(sample.time_ms)
            self.alt_plot.add_liftoff_markers(sample.time_ms, sample.alt_ft)
            self._pending_liftoff = False

        for field, label in self.readout_labels.items():
            value = getattr(sample, field)
            label.setText(f"{value:.4f}" if isinstance(value, float) else str(value))
        self.statusBar().showMessage(f"Logging — {self._skipped_count} skipped lines")

    def on_event(self, name: str) -> None:
        self.event_panel.light(name)
        if name.startswith("LIFTOFF"):
            self._pending_liftoff = True

    def _reset_display(self) -> None:
        self.temp_plot.clear_data()
        self.alt_plot.clear_data()
        self.baro_plot.clear_data()
        self.accel_plot.clear_data()
        self.gyro_plot.clear_data()
        self.event_panel.reset()
        self._pending_liftoff = False
        self.mach_label.setText("--")
        for label in self.readout_labels.values():
            label.setText("--")

    def on_boot_line(self, text: str) -> None:
        if not self._logging_started:
            self.statusBar().showMessage(text)

    def on_skipped_line(self) -> None:
        self._skipped_count += 1

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
        self._reset_display()
        self._serial_reader = SerialReader(port, baud)
        self._serial_reader.sample_received.connect(self.on_sample)
        self._serial_reader.event_received.connect(self.on_event)
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
            samples, events = load_log_file(path)
        except LogFileFormatError as exc:
            QMessageBox.critical(self, "Invalid log file", str(exc))
            return

        self.stop_file_playback()
        self._logging_started = False
        self._skipped_count = 0
        self._reset_display()
        self.scrub_slider.setEnabled(True)
        self.scrub_slider.setRange(0, len(samples) - 1)
        self.scrub_slider.setValue(0)

        self._log_player = LogPlayer(samples, events)
        self._log_player.sample_ready.connect(self._on_playback_sample)
        self._log_player.event_ready.connect(self.on_event)
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

    def closeEvent(self, event) -> None:
        self.disconnect_serial()
        self.stop_file_playback()
        super().closeEvent(event)
```

- [ ] **Step 2: Create a new-format sample fixture for manual verification**

Write `sample_data/sample_log_v2.txt` with this exact content (a short synthetic flight: boot text, header, then PAD → LIFTOFF → BOOST → BURNOUT → COAST → APOGEE → CHUTE DEPLOY → descent → LANDED, each event line immediately before its matching-timestep data line, matching the ordering guarantee from Task 1):

```
Initializing Pins
BMP280 Online
System check complete. Logging started.
  TIME  | TEMP |  ALT | BARO | PITCH | ROLL  | YAW  |  ACCX  |  ACCY  |  ACCZ  |  GX  |  GY  |  GZ  |  GYRX  |  GYRY  |  GYRZ | AIRSPD
000001 | 72.0 | 0.0 | 1015.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0
>>> EVENT: LIFTOFF at t=2
000002 | 72.0 | 5.0 | 1014.8 | 1.0 | 0.5 | 0.2 | 0.0 | 0.0 | 1.0 | 3.5 | 0.1 | 0.0 | 2.0 | 1.0 | 0.5 | 20.0
000003 | 71.5 | 40.0 | 1013.0 | 2.0 | 0.8 | 0.5 | 0.0 | 0.0 | 1.0 | 3.6 | 0.1 | 0.0 | 1.5 | 0.8 | 0.3 | 80.0
>>> EVENT: BURNOUT at t=4
000004 | 71.0 | 120.0 | 1009.0 | 3.0 | 1.0 | 0.8 | 0.0 | 0.0 | 1.0 | 0.3 | 0.0 | 0.0 | 0.5 | 0.2 | 0.1 | 150.0
000005 | 70.5 | 200.0 | 1004.0 | 3.5 | 1.2 | 1.0 | 0.0 | 0.0 | 1.0 | 0.2 | 0.0 | 0.0 | 0.1 | 0.1 | 0.0 | 90.0
>>> EVENT: APOGEE at t=6
000006 | 70.0 | 250.0 | 1000.0 | 3.6 | 1.2 | 1.0 | 0.0 | 0.0 | 1.0 | 0.1 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | -2.0
000007 | 70.0 | 240.0 | 1000.5 | 3.6 | 1.2 | 1.0 | 0.0 | 0.0 | 1.0 | 0.1 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | -35.0
>>> EVENT: CHUTE DEPLOY (inferred) at t=8
000008 | 70.0 | 220.0 | 1001.2 | 3.6 | 1.2 | 1.0 | 0.0 | 0.0 | 1.0 | 2.5 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | -15.0
000009 | 70.5 | 100.0 | 1006.0 | 3.5 | 1.1 | 1.0 | 0.0 | 0.0 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | -14.0
>>> EVENT: LANDED at t=10
000010 | 72.0 | 1.0 | 1015.0 | 3.5 | 1.1 | 1.0 | 0.0 | 0.0 | 1.0 | 1.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0
```

- [ ] **Step 3: Run the existing automated test suite**

Run: `pytest -v`
Expected: PASS (all tests from Tasks 2 and 3 still green; confirms nothing in this rewrite broke the parser/file-source contracts).

- [ ] **Step 4: Manual end-to-end verification**

```bash
python -m arduino_viz.main
```

In the app: select "Load File", open `sample_data/sample_log_v2.txt`, click Play. Confirm:
- All 5 event boxes (LIFTOFF, BURNOUT, APOGEE, CHUTE DEPLOY, LANDED) light up in order as playback passes t=2,4,6,8,10.
- The Environment tab's Altitude plot shows a vertical dashed line at the liftoff time and a horizontal dashed line at the liftoff altitude (0.0 ft), and the Temperature/Barometric plots show the same vertical line.
- The readout panel shows numeric values for every field including `yaw`, `gx_raw`/`gy_raw`/`gz_raw`, `airspeed_fps`, and the appended `mach` row updates as airspeed changes.
- The attitude indicator visibly moves (pitch ladder, yaw ring, numeric overlay) as pitch/roll/yaw change across the file.
- Scrub the slider back to the start — event boxes stay lit (by design, see Global Constraints), everything else resets correctly if you reload the file.

Once the `.ino` from Task 1 is flashed to real hardware, repeat this same check against "Live Serial" mode to confirm the live path behaves identically.

- [ ] **Step 5: Commit**

```bash
git add arduino_viz/main_window.py sample_data/sample_log_v2.txt
git commit -m "feat: wire event pipeline, dials, and attitude detail into MainWindow"
```
