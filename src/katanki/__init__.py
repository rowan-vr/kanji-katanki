"""Kanji Katanki add-on bootstrap. Core imports also work outside Anki."""

import logging
from importlib.util import find_spec

logger = logging.getLogger(f"addon.{__name__}")
logger.addHandler(logging.NullHandler())


def bootstrap() -> None:
    if find_spec("aqt") is None:
        return
    try:
        from .anki.integration import register

        register()
    except Exception:
        logger.exception("Kanji Katanki could not initialize")
        try:
            from aqt.utils import showWarning

            showWarning("Kanji Katanki could not initialize. See Anki's console for details.")
        except Exception:
            logger.exception("Could not display the Kanji Katanki startup warning")


bootstrap()
