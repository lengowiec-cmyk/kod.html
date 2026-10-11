"""Classic ribbon layout using existing application actions."""
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QFrame


class ClassicRibbon(QWidget):
    def __init__(self, groups, parent=None):
        super().__init__(parent)
        self.setObjectName('ClassicRibbon')
        row = QHBoxLayout(self)
        row.setContentsMargins(5, 2, 5, 2)
        row.setSpacing(0)
        for title, actions in groups:
            panel = QWidget(self)
            layout = QVBoxLayout(panel)
            layout.setContentsMargins(6, 3, 6, 2)
            buttons = QHBoxLayout()
            buttons.setSpacing(2)
            for action in actions:
                button = QToolButton(panel)
                button.setDefaultAction(action)
                button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
                button.setIconSize(QSize(25, 25))
                button.setMinimumHeight(54)
                buttons.addWidget(button)
            layout.addLayout(buttons)
            label = QLabel(title, panel)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setObjectName('RibbonGroupLabel')
            layout.addWidget(label)
            row.addWidget(panel)
            line = QFrame(self)
            line.setFrameShape(QFrame.Shape.VLine)
            row.addWidget(line)
        row.addStretch()
