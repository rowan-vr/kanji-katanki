"""Offer setup once per collection, after Anki reaches an idle deck list."""

import logging

logger = logging.getLogger(f"addon.{__name__}")
COMPLETED_KEY = "katanki_onboarding_completed"


class FirstRunSetup:
    def __init__(self, mw, timer):
        self.mw = mw
        self.timer = timer
        self.pending_collection = None
        timer.setInterval(500)
        timer.timeout.connect(self.run_pending)

    def profile_opened(self):
        self.close()
        collection = self.mw.col
        if collection is not None and not collection.get_config(COMPLETED_KEY, False):
            self.pending_collection = collection
            self.timer.start()

    def close(self):
        self.timer.stop()
        self.pending_collection = None

    def run_pending(self):
        collection = self.pending_collection
        if collection is None or self.mw.col is not collection:
            self.close()
            return
        if (
            self.mw.state != "deckBrowser"
            or self.mw.app.activeModalWidget() is not None
            or self.mw.progress.busy()
            or getattr(self.mw, "_katanki_refresh_running", False)
        ):
            return
        self.close()
        try:
            from ..ui.onboarding import open_onboarding

            open_onboarding(self.mw)
        except Exception:
            logger.exception("Katanki setup could not open; restart it from Settings")


def register(mw, hooks):
    from aqt.qt import QTimer

    controller = FirstRunSetup(mw, QTimer(mw))
    mw._katanki_onboarding = controller
    hooks.profile_did_open.append(controller.profile_opened)
    hooks.profile_will_close.append(controller.close)
