import math
import sys

sys.path.insert(0, ".")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from arduino_viz.log_format import Sample
from arduino_viz.main_window import MainWindow

app = QApplication(sys.argv)
win = MainWindow()
win.resize(1000, 650)
win.show()

state = {"i": 0}


def tick():
    i = state["i"]
    sample = Sample(
        time_ms=i * 100, temp_f=70.0 + 0.01 * i, alt_ft=0.0, baro_hpa=1015.0,
        pitch=math.sin(i / 20), roll=math.cos(i / 15), yaw=0.1 * i,
        accx=0.01 * math.sin(i / 5), accy=0.01 * math.cos(i / 5), accz=0.9996,
        gx_raw=1.0, gy_raw=0.0, gz_raw=0.0,
        gyrx=0.05 * math.sin(i / 3), gyry=0.02, gyrz=-0.09,
        airspeed_fps=5.0 * math.sin(i / 30),
    )
    win.on_sample(sample)
    state["i"] += 1


timer = QTimer()
timer.timeout.connect(tick)
timer.start(50)

sys.exit(app.exec())
