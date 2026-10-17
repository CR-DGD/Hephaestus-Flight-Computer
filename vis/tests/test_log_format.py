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
