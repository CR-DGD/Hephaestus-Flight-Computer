# Postflight Vis — Events, Airspeed/Yaw/G-load, Attitude Detail — Design Spec

Date: 2026-09-01
Status: Draft
Supersedes/extends: `2026-08-22-arduino-telemetry-visualizer-design.md` (that
spec's Architecture/Components/Data flow/Dependencies still apply except
where noted below — this doc only covers the delta.)

## Purpose

The `.ino` (Hephaestus flight computer) now emits more than the original
12-field log the vis app was built against: YAW, AIRSPD, and flight-event
lines (`LIFTOFF`/`BURNOUT`/`APOGEE`/`CHUTE DEPLOY`/`LANDED`) already exist in
firmware. This spec:

1. Resyncs the parser to the current (and one additional, see below) `.ino`
   log format — a correctness prerequisite, not optional.
2. Adds an event pipeline so the app reacts to `>>> EVENT: ...` lines
   instead of silently counting them as skipped.
3. Adds true per-axis g-load (the current `ACCX/Y/Z` are a unit vector,
   direction only — a firmware change is needed for real magnitude).
4. Extends the attitude indicator (yaw, pitch ladder, compass ring, numeric
   overlay) and the readout panel (g-load, airspeed, altitude, mach).
5. Adds a launch-conditions overlay (liftoff time + altitude) on the plots
   and an event indicator panel ("boxes that light up").

## `.ino` delta (prerequisite)

One additional firmware change beyond what's already shipped: log the raw
(non-normalized) vertical-axis-remapped accel, `accelRawMapped`, as three
more columns — `GX | GY | GZ`, in g's. This value is already computed in
`loop()` for the airspeed complementary filter; this only adds printing it.
Inserted after `ACCZ`, before `GYRX`.

Full data-line format after this change (17 fields):

```
TIME | TEMP | ALT | BARO | PITCH | ROLL | YAW | ACCX | ACCY | ACCZ | GX | GY | GZ | GYRX | GYRY | GYRZ | AIRSPD
```

Event lines are unchanged from what's already shipped:
`>>> EVENT: <name> at t=<logstep>`, where `<name>` is one of `LIFTOFF`,
`BURNOUT`, `APOGEE`, `CHUTE DEPLOY (inferred)`, `LANDED`.

**Ordering guarantee the rest of this design relies on:** in `loop()`,
flight-event detection (and its `Serial.print`) runs *before*
`formatpacket()`. So an event line for a given loop iteration is always
printed immediately before that iteration's data line, never after. The vis
app uses this to attach launch-condition values (e.g. altitude) to an event
that itself doesn't carry them.

## Log format corrections

The current parser also has two latent unit bugs, being fixed here since the
whole format is being rewritten anyway:

| Field | Old (wrong) assumption | Actual |
|---|---|---|
| TEMP | raw/10 → °C | already °F, no scaling |
| ALT | raw → meters | already feet |
| GYRX/Y/Z | rad/s | deg/s (MPU configured for ±1000 deg/s, divided by the 32.8 LSB/(deg/s) sensitivity) |

`Sample` fields are renamed to match reality: `temp_c`→`temp_f`,
`alt_m`→`alt_ft`. `main_window.py`'s "Gyroscope (rad/s)" plot title is
corrected to "(deg/s)".

## `Sample` schema (new)

```python
@dataclass
class Sample:
    time_ms: int       # actually the board's loop counter, not real ms — unchanged, pre-existing naming
    temp_f: float
    alt_ft: float
    baro_hpa: float
    pitch: float        # deg
    roll: float          # deg
    yaw: float            # deg [NEW]
    accx: float           # unit vector, direction only (NOT g-force) — unchanged meaning
    accy: float
    accz: float
    gx_raw: float          # true g-load [NEW]
    gy_raw: float
    gz_raw: float
    gyrx: float            # deg/s (label fix only, values unchanged)
    gyry: float
    gyrz: float
    airspeed_fps: float    # ft/s [NEW]
```

`_FIELD_COUNT` becomes 17. Field order in `parse_line` matches the `.ino`
column order above.

Mach is *not* a `Sample` field — it's derived in the UI layer (see below),
since it depends on two existing fields and isn't logged itself.

## Event parsing

New function in `log_format.py`:

```python
_EVENT_LINE = re.compile(r"^>>> EVENT: (.+?) at t=(\d+)\s*$")

def parse_event_line(line: str) -> Optional[tuple[str, int]]:
    """Returns (name, time_step) or None. Name is the raw text between
    'EVENT: ' and ' at t=', e.g. 'CHUTE DEPLOY (inferred)'."""
```

Consumers match event names by prefix (`name.startswith("CHUTE DEPLOY")`)
rather than exact match, so the `(inferred)` qualifier doesn't need special
handling everywhere it's checked.

## Event pipeline

**Live (`serial_source.py`):** in `SerialReader.run()`, when a line fails
`parse_line`, try `parse_event_line` before falling through to
`boot_line`/`skipped_line`. On a match, emit a new signal
`event_received(str)` (the name) instead of counting it as skipped.

**File replay (`file_source.py`):**

- `load_log_file` returns `(samples, events)` — `events` is
  `list[tuple[int, str]]` (time_step, name), collected the same pass as
  samples. Only `LogFileFormatError` trigger (no samples found) is
  unchanged; a file with samples but zero events is valid.
- `LogPlayer.__init__` takes an additional `events` param (default `[]`),
  sorted by time_step, plus an internal cursor. New signal
  `event_ready(str)`.
- In `_emit_next`, **before** emitting the sample at the current index, fire
  every not-yet-fired event whose `time_step <= sample.time_ms`. This
  preserves the live-mode ordering guarantee (event before its matching
  data line).
- `seek()` (slider scrub) does not retroactively fire skipped events, same
  as it doesn't replay skipped samples — scrubbing jumps state, it doesn't
  replay history. Event boxes are one-shot latches for the session, so this
  is a display-only quirk (a skipped event's box just won't have lit yet if
  you scrub past it), not a data-loss issue.

## UI components

### `EventPanel` (new, `event_panel.py`)

A `QWidget` with 5 fixed-name boxes (`QLabel`s with a stylesheet-driven
background: gray = not yet occurred, green = occurred) for `LIFTOFF`,
`BURNOUT`, `APOGEE`, `CHUTE DEPLOY`, `LANDED`. One method:
`light(name: str)` — finds the box whose key the given name starts with and
marks it lit (idempotent; already-lit boxes ignore repeats). `reset()`
clears all boxes back to gray, called from `MainWindow._reset_display()`.

### `AttitudeIndicator` (`attitude_widget.py`, extended)

- `set_orientation(pitch, roll, yaw)` — `yaw` is a new required param.
- Pitch ladder: horizontal tick lines every 10° (light, every 30° labeled
  with degree text), drawn in the same rotated/translated painter frame as
  the existing horizon rectangle so they move correctly with pitch/roll.
- Yaw compass ring: a ring of tick marks around the widget's perimeter,
  drawn in an *unrotated* frame (compass rings don't roll with the
  aircraft), rotated as a whole by `-yaw` so it reads like a heading
  indicator; a fixed pointer at top marks current heading.
- Numeric overlay: small text (e.g. top-left corner) showing
  `P:{pitch:.0f} R:{roll:.0f} Y:{yaw:.0f}`.

### Readout panel (`main_window.py`, extended)

No new widget needed — the existing `QFormLayout` loop over
`Sample.__dataclass_fields__` already picks up `yaw`, `gx_raw/gy_raw/gz_raw`,
and `airspeed_fps` automatically once they're `Sample` fields. One addition:
after that loop, append one more `QLabel` row for `mach`, computed (not
looped) in `on_sample`:

```python
temp_c = (sample.temp_f - 32) * 5 / 9
speed_of_sound_mps = 331.3 + 0.6 * temp_c
airspeed_mps = sample.airspeed_fps / 3.28084
mach = airspeed_mps / speed_of_sound_mps
```

### Launch-conditions overlay

`MainWindow` gains `self._pending_liftoff = False`. `on_event(name)`: if
`name.startswith("LIFTOFF")`, sets `self._pending_liftoff = True` (in
addition to lighting the event panel box, always). In `on_sample`: if
`self._pending_liftoff` is set, capture `self._liftoff_time = sample.time_ms`
and `self._liftoff_alt = sample.alt_ft`, clear the flag, and draw the
markers once:

- A vertical `pyqtgraph.InfiniteLine` at `x=self._liftoff_time` on the
  altitude, temperature, and barometric-pressure plots.
- A horizontal `InfiniteLine` at `y=self._liftoff_alt` on the altitude plot
  (the pad-altitude reference).

Markers are added once per connection/file (guarded by the same flag logic)
and cleared in `_reset_display()` along with everything else.

### `on_event` wiring

`MainWindow.on_event(name: str)` is the single entry point connected to both
`SerialReader.event_received` and `LogPlayer.event_ready`. It: (1) calls
`self.event_panel.light(name)`, (2) runs the liftoff-capture check above.
`_reset_display()` additionally resets `event_panel`, `_pending_liftoff`,
`_liftoff_time`/`_liftoff_alt`, and removes any `InfiniteLine`s previously
added.

## Existing-plot correction

The Accelerometer tab plot (`accx/accy/accz`) keeps showing the unit-vector
values (still useful for tilt/direction), but its title changes from
"Accelerometer (g)" to "Accelerometer (direction, unit vector)" so it isn't
mistaken for the new true-g readouts, which are numbers-only (no new plot
tab — out of scope, see below).

## Testing

- `log_format.py`: extend existing pytest coverage for the new 17-field
  line (with realistic GX/GY/GZ, YAW, AIRSPD values), the corrected
  units (no `/10` on temp), and `parse_event_line` for all 5 event names
  including the parenthesized `CHUTE DEPLOY (inferred)` — plus non-matches
  (data lines, boot text) returning `None`.
- `file_source.py`: extend to cover `load_log_file` returning events
  alongside samples, and `LogPlayer` firing `event_ready` before the
  corresponding `sample_ready` for a given time_step.
- Manual pass (same as the original spec's testing note — type checks don't
  catch a mis-wired dial): replay a sample log with events through file
  mode, confirm all 5 boxes light in order, confirm the liftoff overlay
  lines land at the right point, confirm mach/g-load readouts look sane
  against known values; then repeat live against the board once the `.ino`
  change is flashed.

## Out of scope (YAGNI)

- Custom-painted gauge widgets for g-load/airspeed/altitude/mach — plain
  numeric readouts were chosen (see design discussion); revisit only if
  numbers prove hard to read at a glance in practice.
- A dedicated time-series plot tab for the new raw g-load columns — only
  the instantaneous readout was requested.
- Un-latching event boxes on scrub-back, or replaying skipped events when
  seeking — event boxes are a "did this happen" record for the
  file/session, not a live current-state indicator.
- Overlaying every event (burnout/apogee/chute/landed) as plot markers —
  only launch conditions (liftoff) were requested for the overlay; the
  event panel already covers the other four.
