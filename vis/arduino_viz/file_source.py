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
                name, time_step = event
                events.append((time_step, name))

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
        if self._index < len(self._samples):
            target_t = self._samples[self._index].time_ms
            skipped = sum(1 for t, _ in self._events if t <= target_t)
            self._event_cursor = max(self._event_cursor, skipped)  # advance-only

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
