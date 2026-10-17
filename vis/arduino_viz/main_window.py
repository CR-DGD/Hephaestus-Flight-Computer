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
