"""Coalesce automatic triggers and wait for an idle deck list before refreshing."""

import logging

from ..config import load_settings

logger = logging.getLogger(f"addon.{__name__}")


class AutomaticRefresh:
    def __init__(self, mw, timer):
        self.mw = mw
        self.pending_collection = None
        self.timer = timer
        timer.setInterval(1000)
        timer.timeout.connect(self.run_pending)

    def request(self, trigger):
        collection = self.mw.col
        if collection is None:
            return
        try:
            settings = load_settings(collection)
            if not settings.refresh.enabled or not getattr(settings.refresh, trigger):
                return
        except Exception:
            logger.exception("Could not read automatic refresh settings; review Katanki Settings")
            return
        self.pending_collection = collection
        self.timer.start()

    def profile_opened(self):
        self.request("on_profile_open")

    def sync_finished(self):
        self.request("after_sync")

    def close(self):
        self.pending_collection = None
        self.timer.stop()

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
            settings = load_settings(collection)
            if (
                not settings.refresh.enabled
                or not (settings.refresh.on_profile_open or settings.refresh.after_sync)
                or not settings.sources
            ):
                return
            from ..ui.refresh import open_refresh

            open_refresh(self.mw, automatic=True)
        except Exception:
            logger.exception("Automatic refresh failed; try Katanki → Refresh or review Settings")


def register(mw, hooks):
    from aqt.qt import QTimer

    controller = AutomaticRefresh(mw, QTimer(mw))
    mw._katanki_automatic_refresh = controller
    hooks.profile_did_open.append(controller.profile_opened)
    hooks.sync_did_finish.append(controller.sync_finished)
    hooks.profile_will_close.append(controller.close)
