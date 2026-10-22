"""Menu integration for read-only collection discovery."""

import logging

from aqt import mw
from aqt.qt import QAction, QMenu
from aqt.utils import showWarning

logger = logging.getLogger(f"addon.{__name__}")
MENU_NAME = "katanki_menu"


def analyze_collection() -> None:
    try:
        if mw is None or mw.col is None:
            showWarning("Open an Anki profile before using Kanji Katanki.")
            return
        from ..ui.discovery import open_discovery

        open_discovery(mw)
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
    logger.info("Registered Kanji Katanki menu")
