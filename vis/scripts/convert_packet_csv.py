"""Convert sample_data/packet_data.csv into the app's pipe-delimited log
format, so it can be loaded via the "Load File" source in the GUI.

Mapping (per user instruction):
- Value 1 -> ALT (as-is)
- Value 2 -> TEMP (scaled by *10 so the parser's /10 unscaling round-trips
  back to the original value)
- RSSI    -> ignored (no field in the app's log format)
- BARO, PITCH, ROLL, ACCX/Y/Z, GYRX/Y/Z -> not present in this CSV, filled
  with 0
- TIME    -> the CSV has no timestamps, so this assigns a synthetic
  100ms-per-row timeline (arbitrary placeholder, easy to change below)
"""
import csv
import os

INPUT_PATH = "sample_data/packet_data.csv"
OUTPUT_PATH = "sample_data/packet_data_log.txt"
STEP_MS = 100

HEADER = "  TIME  | TEMP |  ALT | BARO | PITCH | ROLL  |  ACCX  |  ACCY  |  ACCZ  |  GYRX  |  GYRY  |  GYRZ"


def convert() -> int:
    lines = [HEADER]
    with open(INPUT_PATH, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            time_ms = i * STEP_MS
            alt_m = float(row["Value 1"])
            temp_raw = float(row["Value 2"]) * 10.0
            line = (
                f"{time_ms:06d} | {temp_raw:.1f} | {alt_m:.2f} | 0 | 0 | 0 | "
                f"0 | 0 | 0 | 0 | 0 | 0"
            )
            lines.append(line)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return len(lines) - 1  # exclude header


if __name__ == "__main__":
    count = convert()
    print(f"Wrote {OUTPUT_PATH} with {count} data rows")
