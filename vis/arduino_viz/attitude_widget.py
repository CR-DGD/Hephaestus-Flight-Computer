from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget


class AttitudeIndicator(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pitch = 0.0  # degrees
        self._roll = 0.0  # degrees
        self._yaw = 0.0  # degrees
        self.setMinimumSize(150, 150)

    def set_orientation(self, pitch: float, roll: float, yaw: float) -> None:
        self._pitch = pitch
        self._roll = roll
        self._yaw = yaw
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        side = min(self.width(), self.height())
        painter.translate(self.width() / 2, self.height() / 2)

        pitch_deg = self._pitch
        roll_deg = self._roll
        pixels_per_degree = side / 90.0

        painter.save()
        painter.rotate(-roll_deg)
        painter.translate(0, pitch_deg * pixels_per_degree)

        half = side * 2
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(60, 120, 200)))
        painter.drawRect(QRectF(-half, -half, 2 * half, half))
        painter.setBrush(QBrush(QColor(120, 80, 40)))
        painter.drawRect(QRectF(-half, 0, 2 * half, half))

        painter.setPen(QPen(Qt.white, 2))
        painter.drawLine(QPointF(-half, 0), QPointF(half, 0))

        self._draw_pitch_ladder(painter, side, pixels_per_degree)
        painter.restore()

        self._draw_yaw_ring(painter, side)

        painter.setPen(QPen(Qt.yellow, 3))
        painter.drawLine(QPointF(-side * 0.25, 0), QPointF(-side * 0.08, 0))
        painter.drawLine(QPointF(side * 0.08, 0), QPointF(side * 0.25, 0))
        painter.drawEllipse(QPointF(0, 0), 3, 3)

        self._draw_numeric_overlay(painter, side)

    def _draw_pitch_ladder(self, painter: QPainter, side: float, pixels_per_degree: float) -> None:
        painter.setPen(QPen(Qt.white, 1))
        font = QFont()
        font.setPointSize(max(6, int(side * 0.05)))
        painter.setFont(font)
        for deg in range(-80, 81, 10):
            if deg == 0:
                continue
            y = -deg * pixels_per_degree
            half_width = side * (0.12 if deg % 30 == 0 else 0.06)
            painter.drawLine(QPointF(-half_width, y), QPointF(half_width, y))
            if deg % 30 == 0:
                painter.drawText(QPointF(half_width + 4, y + 4), str(deg))

    def _draw_yaw_ring(self, painter: QPainter, side: float) -> None:
        radius = side * 0.42
        painter.save()
        painter.rotate(-self._yaw)
        painter.setPen(QPen(Qt.white, 1))
        font = QFont()
        font.setPointSize(max(6, int(side * 0.045)))
        painter.setFont(font)
        for heading in range(0, 360, 30):
            painter.save()
            painter.rotate(heading)
            painter.drawLine(QPointF(0, -radius), QPointF(0, -radius + side * 0.05))
            painter.drawText(QPointF(-8, -radius + side * 0.09 + 8), str(heading))
            painter.restore()
        painter.restore()

        painter.setPen(QPen(Qt.red, 2))
        painter.drawLine(QPointF(0, -radius - 4), QPointF(0, -radius + 6))

    def _draw_numeric_overlay(self, painter: QPainter, side: float) -> None:
        painter.setPen(QPen(Qt.white, 1))
        font = QFont()
        font.setPointSize(max(7, int(side * 0.06)))
        painter.setFont(font)
        text = f"P:{self._pitch:.0f} R:{self._roll:.0f} Y:{self._yaw:.0f}"
        painter.drawText(QRectF(-side / 2 + 4, -side / 2 + 4, side - 8, 20), Qt.AlignLeft, text)
