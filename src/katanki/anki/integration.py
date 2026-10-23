"""Top-level Katanki menu and dialog entrypoints."""

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


def settings() -> None:
    try:
        if mw is None or mw.col is None:
            showWarning("Open an Anki profile before using Katanki settings.")
            return
        from ..ui.settings import open_settings

        open_settings(mw)
    except Exception:
        logger.exception("Katanki Settings failed")
        showWarning("Katanki could not open settings. See Anki's console for details.")


def register() -> None:
    if mw is None or mw.menuBar().findChild(QMenu, MENU_NAME) is not None:
        return
    menu = QMenu("Katanki", mw.menuBar())
    menu.setObjectName(MENU_NAME)
    action = QAction("Analyze Collection", menu)
    action.triggered.connect(analyze_collection)
    menu.addAction(action)
    menu.addSeparator()
    settings_action = QAction("Settings…", menu)
    settings_action.triggered.connect(settings)
    menu.addAction(settings_action)
    mw.menuBar().addMenu(menu)
    logger.info("Registered Kanji Katanki menu")
