"""Dictionary source preferences, separate from statistics target lists."""

from .datasets import DatasetSettingsPanel


class DictionarySettingsPanel(DatasetSettingsPanel):
    def __init__(self, owner, choices):
        super().__init__(owner, choices, target_lists=False)
