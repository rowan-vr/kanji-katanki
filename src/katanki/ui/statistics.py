"""Statistics preferences; target-list sources use the shared dataset controls."""

from aqt.qt import QLabel, QTabWidget, QVBoxLayout, QWidget

from .datasets import DatasetSettingsPanel


class StatisticsSettingsPanel(QWidget):
    def __init__(self, owner, choices):
        super().__init__()
        layout = QVBoxLayout(self)
        description = QLabel(
            "Target lists define which kanji you want to study. "
            "They are independent of dictionary coverage and card progress."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        self.tabs = QTabWidget()
        self.tabs.setObjectName("katanki_statistics_settings_tabs")
        self.lists = DatasetSettingsPanel(owner, choices, target_lists=True)
        self.tabs.addTab(self.lists, "Lists")
        layout.addWidget(self.tabs)

    def choices(self):
        return self.lists.choices()
