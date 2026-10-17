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
