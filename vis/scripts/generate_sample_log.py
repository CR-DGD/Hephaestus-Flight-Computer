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
