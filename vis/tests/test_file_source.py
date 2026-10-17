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


def test_log_player_seek_forward_does_not_replay_skipped_events():
    samples = [_sample(t) for t in range(1, 11)]  # time_ms 1..10
    events = [
        (2, "LIFTOFF"),
        (4, "BURNOUT"),
        (6, "APOGEE"),
        (8, "CHUTE"),
        (10, "LANDED"),
    ]
    player = LogPlayer(samples, events)

    received = []
    player.event_ready.connect(lambda name: received.append(("event", name)))
    player.sample_ready.connect(lambda i, s: received.append(("sample", s.time_ms)))

    # Scrub forward to the sample with time_ms=8 (index 7), skipping over
    # LIFTOFF/BURNOUT/APOGEE/CHUTE which are all due by then.
    player.seek(7)
    player._emit_next()

    fired_events = [name for kind, name in received if kind == "event"]
    assert fired_events == [], (
        "seek() should advance the event cursor past already-passed events "
        f"instead of bursting them on the next _emit_next(); got {fired_events}"
    )
    assert ("sample", 8) in received

    # Continue playback forward: the remaining not-yet-seen event (LANDED at
    # t=10) must still fire exactly once, at the correct sample.
    received.clear()
    player._emit_next()  # time_ms=9, nothing due
    player._emit_next()  # time_ms=10, LANDED due
    assert received == [
        ("sample", 9),
        ("event", "LANDED"),
        ("sample", 10),
    ]


def test_log_player_seek_backward_does_not_regress_event_cursor():
    samples = [_sample(t) for t in range(1, 11)]
    events = [(2, "LIFTOFF"), (4, "BURNOUT")]
    player = LogPlayer(samples, events)

    received = []
    player.event_ready.connect(lambda name: received.append(("event", name)))

    player.seek(5)  # time_ms=6, cursor advances past both events
    player._emit_next()
    assert [n for k, n in received if k == "event"] == []

    # Scrubbing backward must not rewind the event cursor and re-fire events.
    player.seek(0)  # time_ms=1
    player._emit_next()
    assert [n for k, n in received if k == "event"] == []
