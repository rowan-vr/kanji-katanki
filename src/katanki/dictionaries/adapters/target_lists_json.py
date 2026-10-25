"""Canonical target-list dataset adapter, also used for personal imports."""

from pathlib import Path

from ...stats.targets import read_target_list


class TargetListsJson:
    def __init__(self, path: Path):
        loaded = read_target_list(path)
        self.target_lists = (loaded.target_list,)
        self.warnings = loaded.warnings
        self.version = loaded.target_list.version
