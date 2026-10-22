"""Minimal host integration; no collection reads or writes yet."""

import logging

from aqt import mw
from aqt.qt import QAction, QMenu
from aqt.utils import showInfo, showWarning

logger = logging.getLogger(__name__)
MENU_NAME = "katanki_menu"


def analyze_collection() -> None:
    try:
        if mw is None or mw.col is None:
            showWarning("Open an Anki profile before using Kanji Katanki.")
            return
        showInfo(
            "Kanji Katanki is loaded.\n\n"
            "Repository and Anki integration setup is complete.\n"
            "Read-only collection discovery will be added in the next phase.\n\n"
            "This command does not read or modify your collection.",
            parent=mw,
            title="Kanji Katanki — Analyze Collection",
        )
    except Exception:
        logger.exception("Kanji Katanki Analyze Collection failed")
        showWarning("Kanji Katanki could not open the dialog. See Anki's console for details.")


def register() -> None:
    if mw is None or mw.form.menuTools.findChild(QMenu, MENU_NAME) is not None:
        return
    menu = QMenu("Kanji Katanki", mw.form.menuTools)
    menu.setObjectName(MENU_NAME)
    action = QAction("Analyze Collection", menu)
    action.triggered.connect(analyze_collection)
    menu.addAction(action)
    mw.form.menuTools.addMenu(menu)
