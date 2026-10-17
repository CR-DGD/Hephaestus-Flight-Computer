import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QSlider, QVBoxLayout, QWidget

sys.path.insert(0, ".")
from arduino_viz.attitude_widget import AttitudeIndicator


class PreviewWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Attitude Indicator Preview")
        self.indicator = AttitudeIndicator()
        self.pitch_slider = QSlider(Qt.Horizontal)
        self.pitch_slider.setRange(-90, 90)
        self.roll_slider = QSlider(Qt.Horizontal)
        self.roll_slider.setRange(-180, 180)
        self.yaw_slider = QSlider(Qt.Horizontal)
        self.yaw_slider.setRange(-180, 180)
        self.pitch_slider.valueChanged.connect(self._update)
        self.roll_slider.valueChanged.connect(self._update)
        self.yaw_slider.valueChanged.connect(self._update)

        layout = QVBoxLayout(self)
        layout.addWidget(self.indicator)
        layout.addWidget(QLabel("Pitch"))
        layout.addWidget(self.pitch_slider)
        layout.addWidget(QLabel("Roll"))
        layout.addWidget(self.roll_slider)
        layout.addWidget(QLabel("Yaw"))
        layout.addWidget(self.yaw_slider)

    def _update(self) -> None:
        self.indicator.set_orientation(
            self.pitch_slider.value(), self.roll_slider.value(), self.yaw_slider.value()
        )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PreviewWindow()
    window.resize(300, 400)
    window.show()
    sys.exit(app.exec())
