"""Top-level Katanki menu and dialog entrypoints."""

import logging
from pathlib import Path

from aqt import mw
from aqt.qt import QAction, QMenu
from aqt.utils import showWarning

logger = logging.getLogger(f"addon.{__name__}")
MENU_NAME = "katanki_menu"


def refresh_and_generate() -> None:
    try:
        if mw is None or mw.col is None:
            showWarning("Open an Anki profile before using Kanji Katanki.")
            return
        from ..ui.refresh import open_refresh

        open_refresh(mw)
    except Exception:
        logger.exception("Kanji Katanki refresh failed")
        showWarning(
            "Kanji Katanki could not refresh. Review Settings or see Anki's console for details."
        )


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
    from aqt import gui_hooks

    from ..dictionaries.updates import configure_storage

    configure_storage(Path(__file__).resolve().parents[1] / "user_files" / "dictionaries")
    gui_hooks.profile_did_open.append(_check_dictionary_updates)
    from .automatic_refresh import register as register_automatic_refresh

    register_automatic_refresh(mw, gui_hooks)
    menu = QMenu("Katanki", mw.menuBar())
    menu.setObjectName(MENU_NAME)
    action = QAction("Refresh and generate Kanji Cards", menu)
    action.triggered.connect(refresh_and_generate)
    menu.addAction(action)
    menu.addSeparator()
    settings_action = QAction("Settings…", menu)
    settings_action.triggered.connect(settings)
    menu.addAction(settings_action)
    mw.menuBar().addMenu(menu)
    logger.info("Registered Kanji Katanki menu")


def _check_dictionary_updates() -> None:
    from ..dictionaries.updates import check_updates, preferences

    if not preferences().get("automatic", False):
        return

    def finished(future):
        try:
            future.result()
        except Exception:
            logger.info("Dictionary update check unavailable; offline defaults remain active")

    mw.taskman.run_in_background(
        lambda: check_updates(automatic=True), finished, uses_collection=False
    )
