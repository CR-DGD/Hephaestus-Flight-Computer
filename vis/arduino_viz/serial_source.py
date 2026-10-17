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
