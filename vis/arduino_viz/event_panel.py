from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

_BOX_KEYS = ["LIFTOFF", "BURNOUT", "APOGEE", "CHUTE DEPLOY", "LANDED"]
_UNLIT_STYLE = "background-color: #444; color: white; padding: 4px; border-radius: 3px;"
_LIT_STYLE = "background-color: #2ecc71; color: black; padding: 4px; border-radius: 3px;"


class EventPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._boxes: dict[str, QLabel] = {}
        layout = QHBoxLayout(self)
        for key in _BOX_KEYS:
            label = QLabel(key)
            label.setStyleSheet(_UNLIT_STYLE)
            self._boxes[key] = label
            layout.addWidget(label)

    def light(self, name: str) -> None:
        for key, label in self._boxes.items():
            if name.startswith(key):
                label.setStyleSheet(_LIT_STYLE)
                return

    def reset(self) -> None:
        for label in self._boxes.values():
            label.setStyleSheet(_UNLIT_STYLE)
