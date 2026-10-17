# Arduino Telemetry Visualizer — Design Spec

Date: 2026-08-22
Status: Approved

## Purpose

Visualize telemetry from an Arduino board logging TIME, TEMP, ALT, BARO,
PITCH, ROLL, ACCX, ACCY, ACCZ, GYRX, GYRY, GYRZ as a pipe-delimited text
stream. The app must support two interchangeable data sources:

1. **Live serial** — read the same pipe-delimited lines directly off a
   USB/serial connection to the board.
2. **Saved SD card log** — read a log file (same format) written by the
   board to an SD card, played back over time rather than dumped all at
   once.

## Log format

Example (from the board's serial monitor):

```
TIME   | TEMP | ALT  | BARO | PITCH | ROLL   | ACCX   | ACCY   | ACCZ   | GYRX   | GYRY   | GYRZ
000002 | 0080 | 0000 | 1015 | 0.003 | -0.000 | 0.0027 | 0.0263 | 0.9996 | 0.0762 | 0.0152 | -0.0915
```

Fields are separated by `|` with surrounding whitespace.

The `HH:MM:SS.mmm -> ` prefix seen in Arduino IDE screenshots is the IDE
Serial Monitor's own "show timestamp" decoration, not part of the raw
serial bytes or the SD card file. The parser ignores it (strips it if
present, since it costs nothing to tolerate).

### Boot sequence (before logging starts)

Before the header/data lines appear, the board prints an arbitrary,
non-fixed sequence of boot/calibration output, e.g.:

```
Initializing Pins
Initializing BMP
BMP ID was: 0x58
Launch pressure: 1015.42
Initializing MPU1
>*****..........>..........These are the Active offsets:
1064.00000,    -1229.00000,    4674.00000,    90.00000,    -71.00000,    25.00000

Initializing MPU2
>*****..........>..........These are the Active offsets:

-3434.00000,    -2011.00000,    4028.00000,    344.00000,    55.00000,    -13.00000

Chip ID: 0x58
BMP280 Online
MPU1 Online
MPU2 Online
System check complete. Logging started.
  TIME  | TEMP |  ALT | BARO | PITCH | ROLL  |  ACCX  |  ACCY  |  ACCZ  |  GYRX  |  GYRY  |  GYRZ
```

Note this also includes lines that are themselves comma-separated
numbers (the offsets dumps) — these must NOT be mistaken for a data
line. The structural check guards against this because it requires
`|`-delimited splitting into exactly 12 fields; a comma-separated line
of 6 numbers doesn't match.

This includes calibration progress dots, a raw offsets CSV line, blank
lines, and free-text status messages — there is no fixed list of
messages to match against. The parser therefore does **not** try to
recognize specific boot strings. Instead it classifies each incoming
line structurally:

- **Data line**: splits on `|` into the expected field count (12) and
  every field parses as a number → emit as a `Sample`.
- **Anything else** (header line, blank lines, calibration/status text,
  partial reads): not a data line. Before the first successful `Sample`
  is parsed, these lines are surfaced verbatim as "boot status" text
  (see UI behavior below). After logging has started, a non-data line
  is just counted as a skipped/malformed line, same as before.

This structural check is what the app uses to know "logging has
started" — the first line that parses as a full `Sample` is the
signal, rather than matching the literal string `"Logging started."`
(which could change or vary by firmware version).

Units (best guess, confirmed as the working assumption — easy to correct
in one place if wrong):

| Field | Meaning | Raw → unit |
|---|---|---|
| TIME | Milliseconds since board boot | as-is (int ms) |
| TEMP | Temperature | raw / 10 → °C (e.g. `0080` → 8.0°C) |
| ALT | Altitude | as-is → meters |
| BARO | Barometric pressure | as-is → hPa |
| PITCH, ROLL | Orientation | as-is → degrees (confirmed against the real board: the original "radians" guess made the attitude indicator wildly overreact to small tilts) |
| ACCX/Y/Z | Acceleration | as-is → g |
| GYRX/Y/Z | Angular rate | as-is → rad/s |

## Architecture

A single-window PySide6 desktop app. Two interchangeable data sources
feed one UI:

- **Serial reader** — background `QThread` (pyserial `readline()` blocks),
  parses each line, emits a `Sample`.
- **Log player** — parses an entire file up front, then a `QTimer`
  replays samples at recorded pace (scaled by a speed multiplier) using
  the TIME column, emitting `Sample` on each tick.

Both sources emit the same `Sample` dataclass through a Qt signal, so the
UI layer is source-agnostic.

## Components

- **`log_format.py`** — pure parser: one line → `Sample | None`.
  Strips an optional `HH:MM:SS.mmm -> ` IDE-timestamp prefix if present,
  then attempts the structural data-line check described above; returns
  `None` for anything that isn't a full numeric data line (header,
  blank, boot/calibration text). Owns all unit conversion
  (TIME→ms, TEMP/10→°C, etc.) in one place. Pure function, no Qt/IO
  dependency — unit-testable in isolation.
- **`serial_source.py`** — enumerates available COM ports (via
  `pyserial.tools.list_ports`), opens the chosen port/baud rate, reads
  lines on a worker `QThread`, parses via `log_format`. Emits
  `sample_received(Sample)` for data lines. Before the first `Sample` is
  seen, also emits `boot_line(str)` for each non-data line so the UI can
  show live boot/status text; emits an `error(str)` signal on
  disconnect/read failure instead of raising into the GUI thread.
- **`file_source.py`** — loads and parses an entire log file up front
  into a list of `Sample`. A `QTimer`-driven player walks the list,
  scheduling each sample's emission based on the delta between
  consecutive TIME values divided by a speed multiplier. Exposes
  play/pause/seek(index)/set_speed(float).
- **`attitude_widget.py`** — custom `QWidget` using `QPainter` to draw an
  artificial-horizon-style indicator (horizon line + aircraft symbol)
  driven by the latest `pitch`/`roll` values.
- **`main_window.py`** — `QMainWindow` composed of:
  - Top bar: a source-mode selector (Live Serial / Open File). Live mode
    shows a port dropdown (with refresh), baud-rate dropdown (default
    115200), and Connect/Disconnect button. File mode shows an Open File
    button plus play/pause, a speed slider, and a scrub slider once a
    file is loaded.
  - Main area: `pyqtgraph` scrolling plots grouped into three tabs/panes
    — Environment (TEMP, ALT, BARO), Accelerometer (ACCX/Y/Z), Gyroscope
    (GYRX/Y/Z). Each plot keeps a bounded rolling buffer (e.g. last 2000
    samples) via `collections.deque(maxlen=...)`.
  - Side panel: the attitude indicator plus a live numeric readout table
    of the most recent `Sample`.
  - Status bar: while connected but before the first `Sample` arrives,
    shows each incoming boot/status line live (e.g. "BMP280 Online");
    once the first `Sample` parses, switches to a "Logging" state (plus
    replay state when in file mode) and a running count of
    skipped/malformed lines seen thereafter.
- **`main.py`** — entry point. Constructs the window, wires whichever
  source is active to the window's `on_sample(Sample)` slot, starts the
  Qt event loop.

## Data flow

```
SerialReader (QThread)  ──┐
                           ├─ sample_received(Sample) ─▶ MainWindow.on_sample
LogPlayer (QTimer)      ──┘                                  │
                                                               ├─ append to per-channel deques → update pyqtgraph curves
                                                               ├─ update attitude_widget(pitch, roll)
                                                               └─ update numeric readout table
```

Only one source is active at a time; switching modes tears down the
previous source (stop thread / stop timer) before starting the new one.

## Error handling

- Malformed or unparseable lines are skipped by `log_format` and counted;
  the count is shown in the status bar rather than raised as an
  exception, so a single garbled serial line never crashes the app.
- Serial errors (port unavailable, cable unplugged mid-session) are
  caught inside `serial_source`'s thread loop and surfaced via an
  `error(str)` signal; `MainWindow` shows the message in the status bar
  and resets the Connect button/UI state to disconnected.
- Opening a file that doesn't match the expected format shows a modal
  dialog identifying the first line that failed to parse, and does not
  start playback.

## Testing

- `log_format.py` gets pytest unit tests: a valid data line (with and
  without an IDE timestamp prefix), the column-header line, blank lines,
  boot/calibration text (progress-dot line, comma-separated offsets line
  — must NOT be mistaken for a data line, "Chip ID:" / "Online" /
  "Logging started." lines — all must return `None`, not error), a
  malformed data-like line (wrong field count), and edge-case numeric
  values (negative ROLL/GYRZ as seen in the sample data).
- The rest of the app (serial I/O, GUI, timed playback) is verified
  manually: replay against a sample log file for the file-source path,
  and a live serial session against the board for the serial path.
  Type-checking/unit tests won't catch a mis-wired plot or a wrong COM
  port, so this manual pass is required before calling either path
  "done."

## Dependencies

`PySide6`, `pyqtgraph`, `pyserial` — plus `pytest` as a dev dependency
for the parser tests.

## Out of scope (YAGNI)

- GPS/mapping (no GPS field in the log).
- Exporting/re-saving data from the app (the SD card already has the
  authoritative log).
- Multi-board / multi-session comparison views.
- Any 3D OpenGL rendering — the 2D `QPainter` attitude indicator is
  sufficient for pitch/roll and avoids an extra rendering dependency.
